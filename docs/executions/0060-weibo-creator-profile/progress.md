**English** | [中文](progress.zh.md)

# Progress

Baseline verified. Read-only upstream audit confirms Weibo has a fixed login config API and a separate single-creator API; core also has a subsequent full-history path which must never be invoked by lookup. Freeze this plan before dependent implementation. Existing Bili capture release is preserved. No production action.

Plan frozen at `83ff442`. Application and repository now accept platform-bound numeric WB profiles and a fixed Weibo homepage, retaining all existing publication fences. Web and supervised runner are being implemented independently. Optional avatar rules are deliberately a narrow design contract verified with synthetic URLs, not an upstream/live-verified list: the locked repository's avatar example is invalid and provides no real CDN URL evidence. Unknown image forms are skipped, preserving nickname and old avatar.

Read-only remaining-platform audits: DY pong uses local HasUserLogin/LOGIN_STATUS and its only profile API is explicitly for another user; KS pong reads a relationship-list GraphQL response and checks result=1, without explicit self authentication. Tieba pong only checks token presence. None suffices for pasted-Cookie remote authentication. XHS single-profile extraction returns userPageData from HTML but the locked source/fixtures do not establish the exact same-response identity/nickname/avatar schema. These remain required follow-up contract-evidence work, not implemented or abandoned features. No guessed self endpoint or public-data success is promoted to authentication.

## Implemented and reviewed

The WB worker imports only the verified client/config/utils, not WB core/login/store, and constructs that real client directly from scoped credentials. Its decorated five-retry request is replaced before the strict config → creator sequence. It reuses the real get/get_creator_info_by_id methods, with exact full query/header/call-order checks and fixed raw response projection. Cookie candidates remain byte-complete in private frames and outgoing headers; saved-session reads only m.weibo.cn. Other five profile platforms remain unsupported.

Service/repository/UI use a fixed platform-bound canonical homepage and preserve the account/operation/generation/auth-revision/receipt fences. Optional image failure keeps nickname and older avatar. Independent review found the new generic CDN union could widen Bili's download scope to Sina: service now validates against the profile's platform before calling the downloader, with four API cases proving cross-platform URLs cause zero calls while nickname succeeds. The reviewer confirmed this fix and found no additional reproducible blocking issue. This is a code review, not live qualification.

Web supports both Bili and WB Cookie/saved-session accounts, one lookup per completed identity, explicit manual retry, and stale-response/account/platform/session isolation. It does not require capture's full-history checkbox. No existing author or archive/export path is renamed. Five remaining profiles, three Cookie validators and all previously open real-world workflow obligations remain required.

Final frozen-source full Python directories passed4729 with23 environment skips; Web635, static/docs/upstream and source-matching wheel/sdist passed. Verification records exact commands, earlier failures and live exclusions. Bilingual implementation commit `315b2ff` has been non-force published to GitHub with fresh-fetch HEAD/origin equality and a clean worktree. This final documentation record is a subsequent bilingual commit; no deployment is implied.
