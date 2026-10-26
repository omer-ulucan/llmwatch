import React from 'react';
import { Badge } from '@/components/ui';
import type { ModelInfo } from '@/types';

export const CapabilityBadges: React.FC<{ model: ModelInfo }> = ({ model }) => (
  <div className="flex flex-wrap gap-1">
    {model.capabilities.tools && <Badge tone="primary">tools</Badge>}
    {model.capabilities.vision && <Badge tone="secondary">vision</Badge>}
    {model.capabilities.reasoning && <Badge tone="secondary">reasoning</Badge>}
    {model.capabilities.json_mode && <Badge>json</Badge>}
    {model.open_weights && <Badge tone="success">open weights</Badge>}
    {model.local && <Badge tone="success">local</Badge>}
  </div>
);
