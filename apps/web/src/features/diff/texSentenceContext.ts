export type LabelInfo = { number: string; page?: string };

export type TexContext = {
  compiled: boolean;
  citations: Record<string, string>;
  labels: Record<string, LabelInfo>;
  bibliography?: Record<string, string>;
};

export const EMPTY_TEX_CONTEXT: TexContext = {
  compiled: false,
  citations: {},
  labels: {},
};
