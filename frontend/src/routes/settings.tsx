/**
 * Component: Settings
 * Purpose: Manage API keys for programmatic access and tenant configurations.
 * WHY: Enterprise-grade API key management with create, list, regenerate, and revoke
 * functionality. Raw keys are displayed once in a modal with copy-to-clipboard support.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { AlertTriangle, Plus, RefreshCw, Trash2, Copy, Check, Key, X, Clock, Hash } from 'lucide-react';
import { settingsApi } from '../api/settings';
import type { ApiKey, CreateApiKeyResponse } from '@/types';

// ── Raw Key Modal ────────────────────────────────────────

interface RawKeyModalProps {
  rawKeyData: CreateApiKeyResponse | null;
  onClose: () => void;
}

const RawKeyModal: React.FC<RawKeyModalProps> = ({ rawKeyData, onClose }) => {
  const [copied, setCopied] = useState(false);

  if (!rawKeyData) return null;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(rawKeyData.raw_key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for non-HTTPS contexts
      const textarea = document.createElement('textarea');
      textarea.value = rawKeyData.raw_key;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="glass-panel rounded-2xl p-8 max-w-lg w-full relative z-10 space-y-6">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Key size={20} className="text-primary" />
            API Key Created
          </h3>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          >
            <X size={20} />
          </button>
        </div>

        <div className="bg-warning/10 border border-warning/30 rounded-xl p-4">
          <p className="text-sm text-warning font-medium">
            Copy this key now. It will not be shown again.
          </p>
        </div>

        <div>
          <label className="text-sm font-medium text-muted-foreground mb-2 block">
            {rawKeyData.name}
          </label>
          <div className="flex gap-2">
            <code className="flex-1 bg-input/50 border border-card-border rounded-xl px-4 py-3 text-foreground font-mono text-sm break-all select-all">
              {rawKeyData.raw_key}
            </code>
            <button
              onClick={handleCopy}
              className="flex items-center justify-center w-12 bg-white/[0.05] hover:bg-white/[0.1] rounded-xl border border-card-border transition-colors cursor-pointer shrink-0"
              title="Copy to clipboard"
            >
              {copied ? (
                <Check size={16} className="text-success" />
              ) : (
                <Copy size={16} />
              )}
            </button>
          </div>
        </div>

        <button
          onClick={onClose}
          className="w-full flex items-center justify-center gap-2 bg-primary text-white px-6 py-2.5 rounded-xl hover:bg-primary-hover shadow-[0_0_20px_rgba(59,130,246,0.2)] hover:shadow-[0_0_30px_rgba(59,130,246,0.4)] transition-all font-medium cursor-pointer"
        >
          I've saved the key
        </button>
      </div>
    </div>
  );
};

// ── Create Key Modal ─────────────────────────────────────

interface CreateKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (name: string) => void;
  isLoading: boolean;
}

const CreateKeyModal: React.FC<CreateKeyModalProps> = ({ isOpen, onClose, onSubmit, isLoading }) => {
  const [name, setName] = useState('');

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (name.trim()) {
      onSubmit(name.trim());
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="glass-panel rounded-2xl p-8 max-w-md w-full relative z-10 space-y-6">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Plus size={20} className="text-primary" />
            Create API Key
          </h3>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-sm font-medium text-muted-foreground mb-1 block">
              Key Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Production SDK, CI Pipeline"
              maxLength={64}
              autoFocus
              className="w-full bg-input/50 border border-card-border rounded-xl px-4 py-2.5 text-foreground focus:outline-none focus:border-primary/50 transition-colors"
            />
            <p className="text-xs text-muted-foreground mt-1">
              A descriptive name to identify this key's purpose.
            </p>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-6 py-2.5 bg-white/[0.05] hover:bg-white/[0.1] rounded-xl border border-card-border transition-colors cursor-pointer font-medium"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!name.trim() || isLoading}
              className="flex-1 flex items-center justify-center gap-2 bg-primary text-white px-6 py-2.5 rounded-xl hover:bg-primary-hover shadow-[0_0_20px_rgba(59,130,246,0.2)] hover:shadow-[0_0_30px_rgba(59,130,246,0.4)] transition-all font-medium cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <div className="w-4 h-4 rounded-full border-t-2 border-white animate-spin" />
              ) : (
                <>
                  <Key size={16} /> Create Key
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// ── Confirm Dialog ───────────────────────────────────────

interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  variant: 'danger' | 'warning';
  onConfirm: () => void;
  onCancel: () => void;
  isLoading: boolean;
}

const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  isOpen, title, message, confirmLabel, variant, onConfirm, onCancel, isLoading,
}) => {
  if (!isOpen) return null;

  const btnClass = variant === 'danger'
    ? 'bg-error text-white hover:bg-error/90 shadow-lg shadow-error/20'
    : 'bg-warning text-black hover:bg-warning/90 shadow-lg shadow-warning/20';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />
      <div className="glass-panel rounded-2xl p-8 max-w-md w-full relative z-10 space-y-6">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <AlertTriangle size={20} className={variant === 'danger' ? 'text-error' : 'text-warning'} />
          {title}
        </h3>
        <p className="text-sm text-foreground/80">{message}</p>
        <div className="flex gap-3 pt-2">
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 px-6 py-2.5 bg-white/[0.05] hover:bg-white/[0.1] rounded-xl border border-card-border transition-colors cursor-pointer font-medium"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isLoading}
            className={`flex-1 flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl font-medium transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${btnClass}`}
          >
            {isLoading ? (
              <div className="w-4 h-4 rounded-full border-t-2 border-white animate-spin" />
            ) : (
              confirmLabel
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

// ── Helper ───────────────────────────────────────────────

function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffDay > 30) return date.toLocaleDateString();
  if (diffDay > 0) return `${diffDay}d ago`;
  if (diffHour > 0) return `${diffHour}h ago`;
  if (diffMin > 0) return `${diffMin}m ago`;
  return 'just now';
}

// ── Main Settings Component ──────────────────────────────

const Settings: React.FC = () => {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [rawKeyData, setRawKeyData] = useState<CreateApiKeyResponse | null>(null);
  const [creating, setCreating] = useState(false);

  // Confirm dialog state
  const [confirmDialog, setConfirmDialog] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    confirmLabel: string;
    variant: 'danger' | 'warning';
    onConfirm: () => void;
  }>({ isOpen: false, title: '', message: '', confirmLabel: '', variant: 'danger', onConfirm: () => {} });
  const [confirmLoading, setConfirmLoading] = useState(false);

  const fetchKeys = useCallback(async () => {
    try {
      setError(null);
      const response = await settingsApi.listApiKeys();
      setKeys(response.data.keys);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load API keys';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchKeys();
  }, [fetchKeys]);

  const handleCreate = async (name: string) => {
    setCreating(true);
    try {
      const response = await settingsApi.createApiKey(name);
      setRawKeyData(response.data);
      setShowCreateModal(false);
      await fetchKeys();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to create API key';
      setError(message);
    } finally {
      setCreating(false);
    }
  };

  const handleRegenerate = (key: ApiKey) => {
    setConfirmDialog({
      isOpen: true,
      title: 'Regenerate API Key',
      message: `This will permanently invalidate the current key "${key.name}" and generate a new one. Any integrations using the old key will stop working immediately.`,
      confirmLabel: 'Regenerate',
      variant: 'warning',
      onConfirm: async () => {
        setConfirmLoading(true);
        try {
          const response = await settingsApi.regenerateApiKey(key.key_id);
          setRawKeyData(response.data);
          setConfirmDialog(prev => ({ ...prev, isOpen: false }));
          await fetchKeys();
        } catch (err: unknown) {
          const message = err instanceof Error ? err.message : 'Failed to regenerate API key';
          setError(message);
        } finally {
          setConfirmLoading(false);
        }
      },
    });
  };

  const handleRevoke = (key: ApiKey) => {
    setConfirmDialog({
      isOpen: true,
      title: 'Revoke API Key',
      message: `This will permanently delete the key "${key.name}". Any integrations using this key will stop working immediately. This action cannot be undone.`,
      confirmLabel: 'Revoke Key',
      variant: 'danger',
      onConfirm: async () => {
        setConfirmLoading(true);
        try {
          await settingsApi.revokeApiKey(key.key_id);
          setConfirmDialog(prev => ({ ...prev, isOpen: false }));
          await fetchKeys();
        } catch (err: unknown) {
          const message = err instanceof Error ? err.message : 'Failed to revoke API key';
          setError(message);
        } finally {
          setConfirmLoading(false);
        }
      },
    });
  };

  const handleDeleteWorkspace = () => {
    const confirmed = window.confirm(
      'Are you sure you want to delete this workspace? This action cannot be reversed.'
    );
    if (confirmed) {
      window.alert('Workspace deletion is not yet implemented. This will be available in a future release.');
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-12">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Organization Settings</h1>
        <p className="text-muted-foreground">Manage API keys and workspace configuration.</p>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-error/10 border border-error/30 rounded-xl p-4 flex items-center justify-between">
          <p className="text-sm text-error">{error}</p>
          <button
            onClick={() => setError(null)}
            className="text-error/60 hover:text-error transition-colors cursor-pointer"
          >
            <X size={16} />
          </button>
        </div>
      )}

      {/* API Keys Section */}
      <div className="glass-panel rounded-2xl p-8 space-y-6">
        <div className="flex items-center justify-between border-b border-card-border pb-4">
          <div>
            <h2 className="text-lg font-semibold">API Keys</h2>
            <p className="text-sm text-muted-foreground mt-1">
              Keys for programmatic access via the <code className="text-xs bg-white/[0.05] px-1.5 py-0.5 rounded">X-API-Key</code> header.
            </p>
          </div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 bg-primary text-white px-5 py-2 rounded-xl hover:bg-primary-hover shadow-[0_0_20px_rgba(59,130,246,0.2)] hover:shadow-[0_0_30px_rgba(59,130,246,0.4)] transition-all font-medium cursor-pointer text-sm"
          >
            <Plus size={16} /> Create Key
          </button>
        </div>

        {/* Loading State */}
        {loading && (
          <div className="flex items-center justify-center py-12">
            <div className="w-8 h-8 rounded-full border-t-2 border-primary animate-spin" />
          </div>
        )}

        {/* Empty State */}
        {!loading && keys.length === 0 && (
          <div className="text-center py-12">
            <Key size={40} className="mx-auto text-muted-foreground/40 mb-4" />
            <p className="text-muted-foreground font-medium">No API keys yet</p>
            <p className="text-sm text-muted-foreground/70 mt-1">
              Create your first key to enable programmatic access to the LLMWatch API.
            </p>
          </div>
        )}

        {/* Key List */}
        {!loading && keys.length > 0 && (
          <div className="space-y-3">
            {keys.map((key) => (
              <div
                key={key.key_id}
                className="flex items-center justify-between bg-white/[0.02] border border-white/[0.04] rounded-xl px-5 py-4 hover:bg-white/[0.04] transition-colors group"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-1.5">
                    <span className="font-medium text-sm truncate">{key.name}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      key.is_active
                        ? 'bg-success/10 text-success border border-success/20'
                        : 'bg-error/10 text-error border border-error/20'
                    }`}>
                      {key.is_active ? 'Active' : 'Revoked'}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-muted-foreground">
                    <span className="font-mono bg-white/[0.04] px-2 py-0.5 rounded">{key.prefix}</span>
                    <span className="flex items-center gap-1">
                      <Clock size={12} />
                      Created {formatRelativeTime(key.created_at)}
                    </span>
                    {key.last_used_at && (
                      <span className="flex items-center gap-1">
                        <Clock size={12} />
                        Last used {formatRelativeTime(key.last_used_at)}
                      </span>
                    )}
                    <span className="flex items-center gap-1">
                      <Hash size={12} />
                      {key.request_count.toLocaleString()} requests
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity ml-4">
                  <button
                    onClick={() => handleRegenerate(key)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-white/[0.05] hover:bg-white/[0.1] rounded-lg border border-card-border transition-colors cursor-pointer text-xs font-medium hover:text-white"
                    title="Regenerate key"
                  >
                    <RefreshCw size={12} /> Regenerate
                  </button>
                  <button
                    onClick={() => handleRevoke(key)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-error/10 hover:bg-error/20 text-error rounded-lg border border-error/20 transition-colors cursor-pointer text-xs font-medium"
                    title="Revoke key"
                  >
                    <Trash2 size={12} /> Revoke
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Danger Zone */}
      <div className="border border-error/30 bg-error/5 rounded-2xl p-8 space-y-4 relative overflow-hidden group hover:bg-error/10 transition-colors">
        <div className="absolute top-0 right-0 w-64 h-64 bg-error/10 rounded-full blur-3xl translate-x-1/2 -translate-y-1/2" />
        <h2 className="text-lg font-semibold text-error flex items-center gap-2">
          <AlertTriangle size={20} /> Danger Zone
        </h2>
        <p className="text-sm text-foreground/80">
          Permanently delete this workspace and all associated logs. This action cannot be reversed.
        </p>
        <button
          onClick={handleDeleteWorkspace}
          className="bg-error text-white px-6 py-2.5 rounded-xl hover:bg-error/90 font-medium transition-colors cursor-pointer relative z-10 shadow-lg shadow-error/20"
        >
          Delete Workspace
        </button>
      </div>

      {/* Modals */}
      <CreateKeyModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onSubmit={handleCreate}
        isLoading={creating}
      />

      <RawKeyModal
        rawKeyData={rawKeyData}
        onClose={() => setRawKeyData(null)}
      />

      <ConfirmDialog
        isOpen={confirmDialog.isOpen}
        title={confirmDialog.title}
        message={confirmDialog.message}
        confirmLabel={confirmDialog.confirmLabel}
        variant={confirmDialog.variant}
        onConfirm={confirmDialog.onConfirm}
        onCancel={() => setConfirmDialog(prev => ({ ...prev, isOpen: false }))}
        isLoading={confirmLoading}
      />
    </div>
  );
};

export default Settings;
