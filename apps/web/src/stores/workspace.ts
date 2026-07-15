/**
 * @deprecated Prefer `stores/workbench`. Kept as thin re-export for any residual imports.
 */
export {
  useWorkbenchStore as useWorkspaceStore,
  fileKindForPath,
  toolAcceptsPath,
  type ToolKind,
  type ViewTab as ViewInstance,
} from "./workbench";
