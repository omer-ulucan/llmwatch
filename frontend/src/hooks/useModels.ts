import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { modelsApi, providersApi } from '@/api/providers';
import type { ModelInfo } from '@/types';

export function useModelCatalog(availableOnly = false) {
  return useQuery({
    queryKey: ['models', { availableOnly }],
    queryFn: () => modelsApi.catalog({ available_only: availableOnly }),
  });
}

export function useProviders() {
  return useQuery({ queryKey: ['providers'], queryFn: providersApi.list });
}

export function usePresets() {
  return useQuery({ queryKey: ['presets'], queryFn: providersApi.presets, staleTime: Infinity });
}

/** Flat list of available models. */
export function useAvailableModels(): { models: ModelInfo[]; defaultId: string | null; isLoading: boolean } {
  const { data, isLoading } = useModelCatalog(true);
  return {
    models: data?.groups.flatMap((g) => g.models) ?? [],
    defaultId: data?.default_model_id ?? null,
    isLoading,
  };
}

/** Picks the default model (or the first one) once models load. */
export function useInitialModel(value: string, setValue: (id: string) => void): void {
  const { models, defaultId } = useAvailableModels();
  useEffect(() => {
    if (value || !models.length) return;
    setValue(defaultId && models.some((m) => m.id === defaultId) ? defaultId : models[0].id);
  }, [value, models, defaultId, setValue]);
}
