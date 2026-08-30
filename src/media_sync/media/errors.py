"""Stable, redaction-safe media download failures."""

_ERRORS: dict[str, tuple[str, bool]] = {
    "locator_invalid": ("asset locator is invalid", False),
    "locator_secret_forbidden": ("asset locator contains non-persistable data", False),
    "locator_refresh_unsupported": ("asset locator refresh is not supported", True),
    "locator_refresh_configuration_invalid": ("asset locator refresh configuration is invalid", False),
    "locator_refresh_asset_not_found": ("asset was not found during locator refresh", False),
    "locator_refresh_schema_changed": ("asset locator refresh output schema is unsupported", False),
    "locator_refresh_asset_mismatch": ("refreshed asset does not match the requested asset", False),
    "locator_refresh_temporary": ("asset locator refresh is temporarily unavailable", True),
    "locator_refresh_result_invalid": ("asset locator refresh returned an invalid result", False),
    "locator_refresh_auth_expired": ("refreshed asset locator authorization expired", True),
    "network_url_invalid": ("network target is invalid", False),
    "network_dns_failed": ("network target could not be resolved", True),
    "network_address_forbidden": ("network target address is forbidden", False),
    "network_dns_mixed": ("network target resolved to mixed address classes", False),
    "download_redirect_invalid": ("download redirect is invalid", False),
    "download_redirect_limit": ("download redirect limit was exceeded", False),
    "download_timeout": ("download time limit was exceeded", True),
    "download_transport": ("download transport failed", True),
    "download_http_retryable": ("download endpoint returned a retryable response", True),
    "download_http_terminal": ("download endpoint returned a terminal response", False),
    "download_header_limit": ("download response headers exceeded a limit", False),
    "download_encoding_invalid": ("download response encoding is invalid", False),
    "download_content_length_invalid": ("download response length is invalid", False),
    "download_range_invalid": ("download range response is invalid", False),
    "download_chunk_limit": ("download response chunk exceeded a limit", False),
    "download_size_limit": ("download exceeded the byte limit", False),
    "download_interrupted": ("download ended before completion", True),
    "download_restart_limit": ("download restart limit was exceeded", True),
    "download_state_invalid": ("partial download state is invalid", True),
    "download_part_busy": ("partial download is owned by another worker", True),
    "media_type_unsupported": ("downloaded media type is unsupported", False),
    "media_type_mismatch": ("downloaded media type does not match its asset kind", False),
    "media_probe_unavailable": ("required local media probe is unavailable", True),
    "media_probe_failed": ("downloaded media failed bounded probing", True),
    "media_probe_mismatch": ("media signature and structural probe disagree", False),
    "archive_blob_missing": ("verified archive blob is missing", True),
    "archive_blob_invalid": ("existing archive blob failed validation", False),
    "archive_blob_busy": ("archive blob is owned by another local operation", True),
    "filesystem_unsafe": ("filesystem object is not safe", False),
    "filesystem_write_failed": ("filesystem write failed", True),
}


class MediaDownloadError(Exception):
    """A fixed-code failure that never embeds remote or secret material."""

    def __init__(self, code: str) -> None:
        try:
            message, retryable = _ERRORS[code]
        except KeyError as exc:  # pragma: no cover - programmer error
            raise ValueError("unknown media download error code") from exc
        self.code = code
        self.retryable = retryable
        self.message = message
        super().__init__(f"{code}: {message}")


__all__ = ["MediaDownloadError"]
