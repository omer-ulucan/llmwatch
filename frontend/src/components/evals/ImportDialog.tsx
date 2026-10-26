/**
 * Create or import a suite from YAML/JSON (pasted or uploaded). Importing a suite
 * whose name exists adds a new version instead of a duplicate.
 */
import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { Upload } from 'lucide-react';
import { evalsApi } from '@/api/evals';
import { getErrorMessage } from '@/api/errors';
import { Button, Dialog, Textarea, toast } from '@/components/ui';

interface ImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initial?: string;
  title?: string;
}

export const ImportDialog: React.FC<ImportDialogProps> = ({ open, onOpenChange, initial = '', title = 'Import a suite' }) => {
  const [content, setContent] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const save = useMutation({
    mutationFn: () => evalsApi.import(content, content.trimStart().startsWith('{') ? 'json' : 'yaml'),
    onSuccess: (suite) => {
      void queryClient.invalidateQueries({ queryKey: ['eval-suites'] });
      toast.success(
        suite.created_suite ? `Created ${suite.name}` : suite.created_version ? `${suite.name} v${suite.version} saved` : `${suite.name} is unchanged`,
      );
      onOpenChange(false);
      navigate(`/evals/suites/${suite.id}`);
    },
    onError: (err) => setError(getErrorMessage(err, 'Import failed')),
  });

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setContent(await file.text());
    setError(null);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description="YAML or JSON with name, prompt ({{ variables }}), optional assertions and cases."
      className="max-w-3xl"
      footer={
        <>
          <label className="mr-auto inline-flex cursor-pointer items-center gap-2 rounded-xl border border-card-border px-3 py-2 text-sm text-muted-foreground hover:text-foreground">
            <Upload size={14} /> Choose file
            <input
              type="file"
              accept=".yaml,.yml,.json"
              className="sr-only"
              onChange={(e) => void onFile(e.target.files?.[0])}
            />
          </label>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!content.trim()}>
            Save suite
          </Button>
        </>
      }
    >
      <Textarea
        value={content}
        onChange={(e) => {
          setContent(e.target.value);
          setError(null);
        }}
        rows={18}
        spellCheck={false}
        className="font-mono text-xs"
        aria-label="Suite definition"
      />
      {error && (
        <p className="mt-2 whitespace-pre-wrap text-sm text-error" role="alert">
          {error}
        </p>
      )}
    </Dialog>
  );
};
