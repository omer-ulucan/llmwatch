/**
 * Component: Settings
 * Purpose: Workspace details, API keys for programmatic access, and deletion.
 * WHY: API keys are shown exactly once when created or rotated (only a hash is
 * stored). Deleting the workspace is irreversible, so it needs the owner, a browser
 * session and the workspace name typed out.
 */
import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { Check, Copy, KeyRound, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { workspaceApi } from '@/api/auth';
import { getErrorMessage } from '@/api/errors';
import { settingsApi } from '@/api/settings';
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  DataTable,
  Dialog,
  EmptyState,
  ErrorState,
  Field,
  Input,
  PageHeader,
  toast,
  type Column,
} from '@/components/ui';
import { useMe } from '@/hooks/useMe';
import { formatDateTime, formatNumber, formatRelative } from '@/lib/format';
import { useStore } from '@/store/useStore';
import type { ApiKey, CreateApiKeyResponse } from '@/types';

const CopyField: React.FC<{ value: string }> = ({ value }) => {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex gap-2">
      <code className="flex-1 overflow-x-auto whitespace-nowrap rounded-xl border border-card-border bg-black/40 px-3 py-2.5 font-mono text-sm">
        {value}
      </code>
      <Button
        variant="secondary"
        onClick={async () => {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
        aria-label="Copy key"
      >
        {copied ? <Check size={16} /> : <Copy size={16} />}
      </Button>
    </div>
  );
};

const NewKeyDialog: React.FC<{ created: CreateApiKeyResponse | null; onClose: () => void }> = ({ created, onClose }) => (
  <Dialog
    open={Boolean(created)}
    onOpenChange={(open) => !open && onClose()}
    title="Copy your API key now"
    description="It won't be shown again. Store it in a secret manager or your CI secrets."
    footer={<Button onClick={onClose}>Done</Button>}
  >
    {created && (
      <div className="space-y-3">
        <CopyField value={created.raw_key} />
        <p className="text-xs text-muted-foreground">
          Send it as the <code className="font-mono">X-API-Key</code> header, or set{' '}
          <code className="font-mono">LLMWATCH_API_KEY</code> for the CLI.
        </p>
      </div>
    )}
  </Dialog>
);

const ApiKeys: React.FC = () => {
  const queryClient = useQueryClient();
  const keys = useQuery({ queryKey: ['api-keys'], queryFn: () => settingsApi.listApiKeys().then((r) => r.data.keys) });
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [created, setCreated] = useState<CreateApiKeyResponse | null>(null);
  const [rotating, setRotating] = useState<ApiKey | null>(null);
  const [revoking, setRevoking] = useState<ApiKey | null>(null);
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ['api-keys'] });

  const create = useMutation({
    mutationFn: () => settingsApi.createApiKey(name.trim()).then((r) => r.data),
    onSuccess: (key) => {
      setCreating(false);
      setName('');
      setCreated(key);
      refresh();
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Could not create the key')),
  });
  const rotate = useMutation({
    mutationFn: (key: ApiKey) => settingsApi.regenerateApiKey(key.key_id).then((r) => r.data),
    onSuccess: (key) => {
      setRotating(null);
      setCreated(key);
      refresh();
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Could not rotate the key')),
  });
  const revoke = useMutation({
    mutationFn: (key: ApiKey) => settingsApi.revokeApiKey(key.key_id),
    onSuccess: () => {
      toast.success('Key revoked');
      setRevoking(null);
      refresh();
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Could not revoke the key')),
  });

  const columns: Column<ApiKey>[] = [
    { key: 'name', header: 'Name', sortValue: (k) => k.name, render: (k) => <span className="font-medium">{k.name}</span> },
    { key: 'prefix', header: 'Key', render: (k) => <code className="font-mono text-xs text-muted-foreground">{k.prefix}</code> },
    { key: 'created', header: 'Created', sortValue: (k) => k.created_at, render: (k) => <span title={formatDateTime(k.created_at)}>{formatRelative(k.created_at)}</span> },
    {
      key: 'used',
      header: 'Last used',
      sortValue: (k) => k.last_used_at ?? '',
      render: (k) => (k.last_used_at ? formatRelative(k.last_used_at) : <span className="text-muted-foreground">never</span>),
    },
    { key: 'requests', header: 'Requests', align: 'right', sortValue: (k) => k.request_count, render: (k) => formatNumber(k.request_count) },
    {
      key: 'actions',
      header: <span className="sr-only">Actions</span>,
      align: 'right',
      render: (k) => (
        <div className="flex justify-end gap-1">
          <Button size="sm" variant="ghost" onClick={() => setRotating(k)}>
            <RefreshCw size={14} /> Rotate
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setRevoking(k)} aria-label={`Revoke ${k.name}`}>
            <Trash2 size={14} />
          </Button>
        </div>
      ),
    },
  ];

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-card-border p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="font-semibold">API keys</h2>
          <p className="text-sm text-muted-foreground">
            For scripts, SDKs and the <code className="font-mono">llmwatch eval</code> CLI. Keys can't manage other keys.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus size={16} /> New key
        </Button>
      </div>
      {keys.error ? (
        <ErrorState error={keys.error} onRetry={() => void keys.refetch()} />
      ) : (
        <DataTable
          columns={columns}
          rows={keys.data ?? []}
          rowKey={(k) => k.key_id}
          loading={keys.isLoading}
          empty={<EmptyState icon={<KeyRound size={28} />} title="No API keys yet" />}
        />
      )}

      <Dialog
        open={creating}
        onOpenChange={setCreating}
        title="New API key"
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreating(false)}>
              Cancel
            </Button>
            <Button onClick={() => create.mutate()} loading={create.isPending} disabled={!name.trim()}>
              Create key
            </Button>
          </>
        }
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) create.mutate();
          }}
        >
          <Field label="Name" htmlFor="key-name" hint="Where it's used, e.g. “GitHub Actions”">
            <Input id="key-name" value={name} maxLength={64} onChange={(e) => setName(e.target.value)} autoFocus />
          </Field>
        </form>
      </Dialog>
      <NewKeyDialog created={created} onClose={() => setCreated(null)} />
      <ConfirmDialog
        open={Boolean(rotating)}
        onOpenChange={(open) => !open && setRotating(null)}
        title={`Rotate “${rotating?.name}”?`}
        description="The current key stops working immediately and a new one is shown once."
        confirmLabel="Rotate key"
        loading={rotate.isPending}
        onConfirm={() => rotating && rotate.mutate(rotating)}
      />
      <ConfirmDialog
        open={Boolean(revoking)}
        onOpenChange={(open) => !open && setRevoking(null)}
        title={`Revoke “${revoking?.name}”?`}
        description="Anything using this key loses access immediately. This can't be undone."
        confirmLabel="Revoke key"
        danger
        loading={revoke.isPending}
        onConfirm={() => revoking && revoke.mutate(revoking)}
      />
    </Card>
  );
};

const DangerZone: React.FC<{ workspaceName: string }> = ({ workspaceName }) => {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState('');
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const logout = useStore((s) => s.logout);
  const remove = useMutation({
    mutationFn: () => workspaceApi.delete(typed),
    onSuccess: () => {
      logout();
      queryClient.clear();
      toast.success('Workspace deleted');
      navigate('/', { replace: true });
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Could not delete the workspace')),
  });
  return (
    <Card className="border-error/20 p-5">
      <h2 className="font-semibold text-error">Delete workspace</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Permanently deletes the workspace with all its users, API keys, providers, logs, traces and evals.
      </p>
      <Button variant="danger" className="mt-4" onClick={() => setOpen(true)}>
        <Trash2 size={16} /> Delete workspace
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={(o) => {
          setOpen(o);
          if (!o) setTyped('');
        }}
        title="Delete this workspace?"
        description="This can't be undone."
        confirmLabel="Delete forever"
        danger
        loading={remove.isPending}
        confirmDisabled={typed !== workspaceName}
        onConfirm={() => remove.mutate()}
      >
        <Field label={`Type “${workspaceName}” to confirm`} htmlFor="confirm-name">
          <Input id="confirm-name" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
        </Field>
      </ConfirmDialog>
    </Card>
  );
};

const Settings: React.FC = () => {
  const { data: me, error, refetch } = useMe();
  return (
    <div className="mx-auto max-w-5xl space-y-6 pb-12">
      <PageHeader title="Settings" description="Workspace, API keys and account." />
      {error ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : (
        <Card className="p-5">
          <h2 className="font-semibold">Workspace</h2>
          <dl className="mt-3 grid grid-cols-1 gap-4 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-muted-foreground">Name</dt>
              <dd className="font-medium">{me?.workspace.name ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Signed in as</dt>
              <dd className="font-medium">{me?.user.email ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Role</dt>
              <dd>{me && <Badge tone={me.user.role === 'owner' ? 'primary' : 'neutral'}>{me.user.role}</Badge>}</dd>
            </div>
          </dl>
        </Card>
      )}
      <ApiKeys />
      {me?.user.role === 'owner' && <DangerZone workspaceName={me.workspace.name} />}
    </div>
  );
};

export default Settings;
