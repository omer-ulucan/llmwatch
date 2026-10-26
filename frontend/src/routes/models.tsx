/**
 * Component: Models
 * Purpose: Manage the workspace's LLM providers and model catalogue.
 * WHY: Everything the chat, agent and evals can call is configured here: provider
 * endpoints and keys (never shown again after saving), and per-model prices and
 * capabilities that drive cost figures and the model pickers.
 */
import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Boxes, Pencil, Plug, Plus, RefreshCw, Star, Trash2 } from 'lucide-react';
import { getErrorMessage } from '@/api/errors';
import { modelsApi, providersApi, type ModelInput, type ProviderInput } from '@/api/providers';
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
  NativeSelect,
  PageHeader,
  SkeletonRows,
  toast,
  type Column,
} from '@/components/ui';
import { CapabilityBadges } from '@/components/models/ModelBadges';
import { priceLabel } from '@/lib/models';
import { useMe } from '@/hooks/useMe';
import { useModelCatalog, usePresets } from '@/hooks/useModels';
import type { Capabilities, ModelInfo, Provider } from '@/types';

const NO_CAPS: Capabilities = { tools: false, vision: false, reasoning: false, json_mode: false };

function useInvalidate() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['models'] });
    void queryClient.invalidateQueries({ queryKey: ['providers'] });
  };
}

// ── Provider dialog ─────────────────────────────────────────

const ProviderDialog: React.FC<{
  open: boolean;
  onOpenChange: (open: boolean) => void;
  provider?: Provider;
}> = ({ open, onOpenChange, provider }) => {
  const { data: presets = [] } = usePresets();
  const invalidate = useInvalidate();
  const editing = Boolean(provider);
  const [preset, setPreset] = useState(provider?.preset ?? 'openai');
  const [name, setName] = useState(provider?.name ?? '');
  const [baseUrl, setBaseUrl] = useState(provider?.base_url ?? '');
  const [apiKey, setApiKey] = useState('');
  const [clearKey, setClearKey] = useState(false);
  const chosen = presets.find((p) => p.id === preset);

  const save = useMutation({
    mutationFn: async () => {
      if (provider) {
        const input: Partial<ProviderInput> = { name, base_url: baseUrl };
        if (apiKey) input.api_key = apiKey;
        else if (clearKey) input.api_key = null;
        return providersApi.update(provider.id, input);
      }
      return providersApi.create({
        name: name || chosen?.label || preset,
        preset,
        base_url: baseUrl || null,
        api_key: apiKey || null,
      });
    },
    onSuccess: (saved) => {
      toast.success(editing ? `Saved ${saved.name}` : `Added ${saved.name}`, {
        description: editing ? undefined : 'Discover its models to start using it.',
      });
      invalidate();
      onOpenChange(false);
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Could not save the provider')),
  });

  const urlChanged = editing && baseUrl !== provider?.base_url && provider?.has_api_key && !apiKey;

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={editing ? `Edit ${provider?.name}` : 'Add a provider'}
      description="Any OpenAI-compatible endpoint works. Keys are encrypted and never shown again."
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => save.mutate()} loading={save.isPending}>
            {editing ? 'Save' : 'Add provider'}
          </Button>
        </>
      }
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        {!editing && (
          <Field label="Type" htmlFor="provider-preset">
            <NativeSelect
              id="provider-preset"
              value={preset}
              onChange={(e) => {
                const next = presets.find((p) => p.id === e.target.value);
                setPreset(e.target.value);
                setName(next?.label ?? '');
                setBaseUrl(next?.base_url ?? '');
              }}
            >
              {presets.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                  {p.local ? ' (local)' : ''}
                </option>
              ))}
            </NativeSelect>
          </Field>
        )}
        <Field label="Name" htmlFor="provider-name">
          <Input
            id="provider-name"
            value={name}
            placeholder={chosen?.label}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Field
          label="Base URL"
          htmlFor="provider-url"
          hint={chosen?.local ? 'From Docker, use host.docker.internal instead of localhost.' : undefined}
          error={urlChanged ? 'Changing the URL removes the saved key unless you enter it again.' : null}
        >
          <Input
            id="provider-url"
            value={baseUrl}
            placeholder={chosen?.base_url || 'https://example.com/v1'}
            onChange={(e) => setBaseUrl(e.target.value)}
          />
        </Field>
        <Field
          label={chosen?.requires_api_key || !chosen ? 'API key' : 'API key (optional)'}
          htmlFor="provider-key"
          hint={provider?.has_api_key ? `Saved key: ${provider.api_key_masked}. Leave empty to keep it.` : undefined}
        >
          <Input
            id="provider-key"
            type="password"
            autoComplete="off"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </Field>
        {provider?.has_api_key && (
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input type="checkbox" checked={clearKey} onChange={(e) => setClearKey(e.target.checked)} />
            Remove the saved key
          </label>
        )}
        <button type="submit" className="hidden" />
      </form>
    </Dialog>
  );
};

// ── Model dialog ────────────────────────────────────────────

const numberOrNull = (value: string): number | null => (value.trim() === '' ? null : Number(value));

const ModelDialog: React.FC<{
  open: boolean;
  onOpenChange: (open: boolean) => void;
  model?: ModelInfo;
  providers: Provider[];
}> = ({ open, onOpenChange, model, providers }) => {
  const invalidate = useInvalidate();
  const [providerId, setProviderId] = useState(model?.provider_id ?? providers[0]?.id ?? '');
  const [modelId, setModelId] = useState(model?.model_id ?? '');
  const [displayName, setDisplayName] = useState(model?.display_name ?? '');
  const [contextWindow, setContextWindow] = useState(model?.context_window?.toString() ?? '');
  const [inputPrice, setInputPrice] = useState(model?.input_price_per_mtok?.toString() ?? '');
  const [outputPrice, setOutputPrice] = useState(model?.output_price_per_mtok?.toString() ?? '');
  const [caps, setCaps] = useState<Capabilities>(model?.capabilities ?? NO_CAPS);
  const [openWeights, setOpenWeights] = useState(model?.open_weights ?? false);

  const save = useMutation({
    mutationFn: () => {
      const input: ModelInput = {
        display_name: displayName || modelId,
        context_window: numberOrNull(contextWindow),
        input_price_per_mtok: numberOrNull(inputPrice),
        output_price_per_mtok: numberOrNull(outputPrice),
        capabilities: caps,
        open_weights: openWeights,
      };
      return model
        ? modelsApi.update(model.id, input)
        : modelsApi.create({ ...input, provider_id: providerId, model_id: modelId });
    },
    onSuccess: () => {
      toast.success(model ? 'Model saved' : 'Model added');
      invalidate();
      onOpenChange(false);
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Could not save the model')),
  });

  const capLabels: [keyof Capabilities, string][] = [
    ['tools', 'Tool calling'],
    ['vision', 'Vision'],
    ['reasoning', 'Reasoning'],
    ['json_mode', 'JSON mode'],
  ];

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={model ? `Edit ${model.display_name}` : 'Add a model'}
      description="Prices are USD per 1M tokens. Leave a price empty if you don't know it: costs then show as unpriced instead of $0."
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!model && (!modelId || !providerId)}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {!model && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Provider" htmlFor="model-provider">
              <NativeSelect id="model-provider" value={providerId} onChange={(e) => setProviderId(e.target.value)}>
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Model id" htmlFor="model-id" hint="As the provider names it, e.g. gpt-4o-mini">
              <Input id="model-id" value={modelId} onChange={(e) => setModelId(e.target.value)} />
            </Field>
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Display name" htmlFor="model-name">
            <Input id="model-name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </Field>
          <Field label="Context window (tokens)" htmlFor="model-context">
            <Input
              id="model-context"
              type="number"
              min={1}
              value={contextWindow}
              onChange={(e) => setContextWindow(e.target.value)}
            />
          </Field>
          <Field label="Input $ / 1M tokens" htmlFor="model-in">
            <Input id="model-in" type="number" min={0} step="any" value={inputPrice} onChange={(e) => setInputPrice(e.target.value)} />
          </Field>
          <Field label="Output $ / 1M tokens" htmlFor="model-out">
            <Input id="model-out" type="number" min={0} step="any" value={outputPrice} onChange={(e) => setOutputPrice(e.target.value)} />
          </Field>
        </div>
        <fieldset>
          <legend className="mb-2 text-sm font-medium">Capabilities</legend>
          <div className="grid grid-cols-2 gap-2 text-sm">
            {capLabels.map(([key, label]) => (
              <label key={key} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={caps[key]}
                  onChange={(e) => setCaps({ ...caps, [key]: e.target.checked })}
                />
                {label}
              </label>
            ))}
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={openWeights} onChange={(e) => setOpenWeights(e.target.checked)} />
              Open weights
            </label>
          </div>
        </fieldset>
      </div>
    </Dialog>
  );
};

// ── Page ────────────────────────────────────────────────────

const ProviderCard: React.FC<{
  provider: Provider;
  models: ModelInfo[];
  canManage: boolean;
  onEditModel: (m: ModelInfo) => void;
}> = ({ provider, models, canManage, onEditModel }) => {
  const invalidate = useInvalidate();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const test = useMutation({
    mutationFn: () => providersApi.test(provider.id),
    onSuccess: (r) =>
      r.ok
        ? toast.success(`${provider.name} is reachable`, {
            description: `${r.model_count} model(s) listed in ${Math.round(r.latency_ms)} ms`,
          })
        : toast.error(`${provider.name}: ${r.error_kind ?? 'error'}`, { description: r.error ?? undefined }),
    onError: (err) => toast.error(getErrorMessage(err, 'Connection test failed')),
  });
  const discover = useMutation({
    mutationFn: () => providersApi.discover(provider.id),
    onSuccess: (r) => {
      toast.success(
        r.added.length ? `Added ${r.added.length} model(s)` : 'No new models',
        { description: `${r.discovered.length} listed by ${provider.name}` },
      );
      invalidate();
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Could not list models')),
  });
  const toggle = useMutation({
    mutationFn: () => providersApi.update(provider.id, { enabled: !provider.enabled }),
    onSuccess: invalidate,
    onError: (err) => toast.error(getErrorMessage(err, 'Could not update the provider')),
  });
  const remove = useMutation({
    mutationFn: () => providersApi.remove(provider.id),
    onSuccess: () => {
      toast.success(`Deleted ${provider.name}`);
      setDeleting(false);
      invalidate();
    },
    onError: (err) => toast.error(getErrorMessage(err, 'Could not delete the provider')),
  });
  const modelUpdate = useMutation({
    mutationFn: ({ id, input }: { id: string; input: ModelInput }) => modelsApi.update(id, input),
    onSuccess: invalidate,
    onError: (err) => toast.error(getErrorMessage(err, 'Could not update the model')),
  });

  const columns: Column<ModelInfo>[] = [
    {
      key: 'name',
      header: 'Model',
      sortValue: (m) => m.display_name,
      render: (m) => (
        <div className="min-w-40">
          <div className="flex items-center gap-1.5 font-medium">
            {m.display_name}
            {m.is_default && <Star size={12} className="fill-warning text-warning" aria-label="default" />}
          </div>
          {m.display_name !== m.model_id && <div className="text-xs text-muted-foreground">{m.model_id}</div>}
        </div>
      ),
    },
    { key: 'caps', header: 'Capabilities', render: (m) => <CapabilityBadges model={m} /> },
    {
      key: 'price',
      header: 'Price',
      sortValue: (m) => m.input_price_per_mtok ?? -1,
      render: (m) => (
        <span className={m.priced ? '' : 'text-warning'} title={m.priced ? undefined : 'Costs show as unpriced until you set a price'}>
          {priceLabel(m)}
        </span>
      ),
    },
    {
      key: 'context',
      header: 'Context',
      sortValue: (m) => m.context_window ?? 0,
      render: (m) => (m.context_window ? m.context_window.toLocaleString() : '—'),
    },
    {
      key: 'actions',
      header: <span className="sr-only">Actions</span>,
      align: 'right',
      render: (m) =>
        canManage ? (
          <div className="flex justify-end gap-1 whitespace-nowrap">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => modelUpdate.mutate({ id: m.id, input: { enabled: !m.enabled } })}
            >
              {m.enabled ? 'Disable' : 'Enable'}
            </Button>
            {!m.is_default && m.enabled && (
              <Button size="sm" variant="ghost" onClick={() => modelUpdate.mutate({ id: m.id, input: { is_default: true } })}>
                Make default
              </Button>
            )}
            <Button size="icon" variant="ghost" aria-label={`Edit ${m.display_name}`} onClick={() => onEditModel(m)}>
              <Pencil size={14} />
            </Button>
          </div>
        ) : null,
    },
  ];

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-card-border p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold">{provider.name}</h3>
            <Badge>{provider.preset_label}</Badge>
            {provider.local && <Badge tone="success">local</Badge>}
            {provider.managed_by_env && <Badge tone="warning" title="Configured through environment variables">env</Badge>}
            {!provider.enabled && <Badge tone="error">disabled</Badge>}
          </div>
          <p className="mt-1 truncate text-xs text-muted-foreground">
            {provider.base_url}
            {provider.has_api_key ? ` · key ${provider.api_key_masked}` : ' · no key'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" onClick={() => test.mutate()} loading={test.isPending}>
            <Plug size={14} /> Test
          </Button>
          {canManage && (
            <>
              <Button size="sm" variant="secondary" onClick={() => discover.mutate()} loading={discover.isPending}>
                <RefreshCw size={14} /> Discover models
              </Button>
              <Button size="sm" variant="ghost" onClick={() => toggle.mutate()}>
                {provider.enabled ? 'Disable' : 'Enable'}
              </Button>
              {!provider.managed_by_env && (
                <>
                  <Button size="icon" variant="ghost" aria-label={`Edit ${provider.name}`} onClick={() => setEditing(true)}>
                    <Pencil size={14} />
                  </Button>
                  <Button size="icon" variant="ghost" aria-label={`Delete ${provider.name}`} onClick={() => setDeleting(true)}>
                    <Trash2 size={14} />
                  </Button>
                </>
              )}
            </>
          )}
        </div>
      </div>
      <DataTable
        columns={columns}
        rows={models}
        rowKey={(m) => m.id}
        empty={
          <EmptyState
            title="No models yet"
            description={canManage ? 'Use "Discover models" to import what the provider offers, or add one by id.' : undefined}
            className="py-8"
          />
        }
      />
      {editing && <ProviderDialog open={editing} onOpenChange={setEditing} provider={provider} />}
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete ${provider.name}?`}
        description="Its models are removed too. Logs and eval results keep their history."
        confirmLabel="Delete provider"
        danger
        loading={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </Card>
  );
};

const Models: React.FC = () => {
  const { data, isLoading, error, refetch } = useModelCatalog(false);
  const { data: me } = useMe();
  const canManage = me?.user.role === 'owner' && me.auth_method === 'jwt';
  const [addingProvider, setAddingProvider] = useState(false);
  const [modelDialog, setModelDialog] = useState<{ open: boolean; model?: ModelInfo }>({ open: false });

  const groups = data?.groups ?? [];
  const providers = groups.map((g) => g.provider);

  return (
    <div className="mx-auto max-w-6xl pb-12">
      <PageHeader
        title="Models"
        description="Providers and the models your workspace can use. Prices drive every cost figure."
        actions={
          canManage && (
            <>
              {providers.length > 0 && (
                <Button variant="secondary" onClick={() => setModelDialog({ open: true })}>
                  <Plus size={16} /> Add model
                </Button>
              )}
              <Button onClick={() => setAddingProvider(true)}>
                <Plus size={16} /> Add provider
              </Button>
            </>
          )
        }
      />
      {!canManage && me && (
        <p className="mb-4 text-sm text-muted-foreground">Only the workspace owner can change providers and models.</p>
      )}
      {isLoading ? (
        <SkeletonRows rows={6} />
      ) : error ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : groups.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Boxes size={28} />}
            title="No providers yet"
            description="Add OpenAI, Gemini, OpenRouter, Groq, Together, or a local Ollama, vLLM or LM Studio server."
            action={canManage && <Button onClick={() => setAddingProvider(true)}>Add a provider</Button>}
          />
        </Card>
      ) : (
        <div className="space-y-6">
          {groups.map((g) => (
            <ProviderCard
              key={g.provider.id}
              provider={g.provider}
              models={g.models}
              canManage={canManage}
              onEditModel={(m) => setModelDialog({ open: true, model: m })}
            />
          ))}
        </div>
      )}
      {addingProvider && <ProviderDialog open={addingProvider} onOpenChange={setAddingProvider} />}
      {modelDialog.open && (
        <ModelDialog
          open={modelDialog.open}
          onOpenChange={(open) => setModelDialog({ open })}
          model={modelDialog.model}
          providers={providers}
        />
      )}
    </div>
  );
};

export default Models;
