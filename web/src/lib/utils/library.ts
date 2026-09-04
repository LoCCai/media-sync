import type {
  LibraryAction,
  LibraryFreshness,
  LibraryInspection,
  LibraryIntegrity,
  ManagedLibraryFile,
  MediaServerAction,
  MediaServerStatus
} from '$lib/types/api';

export interface LibraryInspectionView {
  inspection: LibraryInspection;
  files: ManagedLibraryFile[];
}

const FRESHNESS_LABELS: Record<LibraryFreshness, string> = {
  not_published: '尚未发布',
  current: '与当前内容一致',
  outdated: '需要重新发布',
  blocked: '当前快照不可发布'
};

const INTEGRITY_LABELS: Record<LibraryIntegrity, string> = {
  not_available: '无已发布树',
  unchecked: '尚未检查',
  page_verified: '本页已校验',
  complete: '整树已校验',
  budget_exhausted: '检查预算已用尽',
  drifted: '检测到文件漂移',
  inconsistent: '发布记录不一致'
};

export function libraryFreshnessLabel(value: LibraryFreshness): string {
  return FRESHNESS_LABELS[value];
}

export function libraryIntegrityLabel(value: LibraryIntegrity): string {
  return INTEGRITY_LABELS[value];
}

export function libraryStateTone(
  freshness: LibraryFreshness,
  integrity: LibraryIntegrity
): 'success' | 'warning' | 'danger' | 'info' {
  if (integrity === 'drifted' || integrity === 'inconsistent') return 'danger';
  if (freshness === 'blocked' || integrity === 'budget_exhausted') return 'warning';
  if (freshness === 'current' && integrity === 'complete') return 'success';
  return 'info';
}

export function libraryAllows(inspection: LibraryInspection | null, action: LibraryAction): boolean {
  return inspection?.allowed_actions.includes(action) ?? false;
}

function publicationIdentity(inspection: LibraryInspection): string | null {
  const publication = inspection.publication;
  if (!publication) return null;
  return [
    publication.publication_scope,
    publication.job_id,
    publication.manifest_sha256,
    publication.tree_sha256,
    publication.managed_file_count
  ].join(':');
}

export function mergeLibraryInspectionPage(
  current: LibraryInspectionView | null,
  incoming: LibraryInspection
): LibraryInspectionView {
  const canAppend =
    current !== null &&
    incoming.author_id === current.inspection.author_id &&
    publicationIdentity(incoming) !== null &&
    publicationIdentity(incoming) === publicationIdentity(current.inspection) &&
    incoming.page.start_index === current.inspection.page.next_index;
  return {
    inspection: incoming,
    files: canAppend ? [...current.files, ...incoming.files] : [...incoming.files]
  };
}

export function mediaServerAllows(status: MediaServerStatus | null, action: MediaServerAction): boolean {
  return status?.allowed_actions.includes(action) ?? false;
}

export function mediaServerPosture(status: MediaServerStatus | null): {
  label: string;
  tone: 'success' | 'warning' | 'danger' | 'info';
} {
  if (!status?.configuration.configured) return { label: '未配置', tone: 'info' };
  if (!status.configuration.operations_enabled) return { label: '操作门已关闭', tone: 'warning' };
  if (status.latest_probe?.state === 'succeeded') return { label: '连接已验证', tone: 'success' };
  if (status.latest_probe?.state.startsWith('failed')) return { label: '最近探测失败', tone: 'danger' };
  return { label: '已配置，尚未探测', tone: 'info' };
}
