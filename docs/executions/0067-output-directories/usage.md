**English** | [中文](usage.zh.md)

# Usage and upgrade boundaries

This is the0067 directory feature, not a QR-login fix. Deployment was not performed for the operator.

1. Back up database and media before upgrading. The new schema is0012_library_output_policy; nonempty policy/binding history prevents downgrade rather than dropping location evidence.
2. Keep the existing/data mount. For a separate media disk, give both media-sync and supervisor the same container mount, e.g. host`/srv/media-sync-library` at container`/media-library`. Do not replace all of/data with an empty disk: credentials, database and archive remain there.
3. Both updated services must use the same database. In Settings→media directories enter`/media-library`. Empty platform overrides inherit`/media-library/bili`,`/media-library/dy`, etc. Mount independent platform disks before setting their container paths.
4. Preview shows effective paths without creating files. After save, new work reads the shared policy even from previously started workers. Container-user write permissions are still required.
5. Existing output keeps its old location, typically author folders under/data/library. Preserve a protected platform root via an explicit override when changing the common root; unused platforms can use new locations. Physical migration is not provided; do not rewrite location records manually.
6. If bootstrap reports output_directory_migration_required before policy initialization, restore the original MEDIA_SYNC_EXPORT_DIR and mounts. Old Job scope hashes cannot reconstruct absolute paths; multiple historical roots need a later explicit migration audit.
7. Mount actual output paths read-only into Emby/Jellyfin and configure libraries/scans there. No server API or extra export click is required. Retained text/galleries do not imply video playback support. Optional server linkage remains single-root and never guesses mappings for new platform roots.

Preview/save do not trigger login, history scanning, downloads or server refresh, and do not restart a paused supervisor.
