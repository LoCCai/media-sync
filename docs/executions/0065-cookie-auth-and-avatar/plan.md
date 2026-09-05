**English** | [中文](plan.zh.md)

# Frozen plan

1. Commit before application edits. Preserve locks/dependencies/schema; separate platform modules and tests owned by agents, shared workflow/UI/docs owned by root.

2. DY: one pinned HTTPS GET `https://creator.douyin.com/web/api/media/user/info/`, no target author, no invented query/signature/browser or local Cookie flag proof. Require exact `user.sec_uid` and nickname from the self response; explicitly classify strict success/guest/error subset after source review. Use original implementation of public protocol facts, not copied source. No raw self identity or response in result/logs.

3. KS: real locked KuaiShouClient.post with exactly one POST to `https://www.kuaishou.com/graphql`, fixed `userInfoQuery`, empty variables and no target author. Source requires candidate Cookie's nonempty `kuaishou.web.cp.api_ph` in the exact same-name body field; do not substitute another key or claim all Cookies accepted. Require response data.userInfo positive integer userId and raw bounded name, no errors/guest ambiguity. No browser/sign query/relationships/capture calls or response-body leak.

4. Both self checks reuse private framed guardian/workers, strict bounded JSON/public pinned transport/deadline/no redirects/no ambient proxy, atomic credential/account publication and preservation on candidate failure. Canonicalize cookie runner module under real script execution so imported typed failures reach the correct handler. Test real script/guardian dispatch, isolation and old-credential retention. Missing runtime/source/Cookie prerequisites cannot authenticate.

5. Zhihu: optional avatarUrl only from the exact returned row after urlToken/name checks. Initial source-backed subset is unchanged HTTPS pic2.zhimg.com/{32 lowercase hex}_l.jpg, not all current CDN forms. Reuse isolated no-Cookie avatar download/decode, same-origin PNG, limits and previous-avatar retention. No new endpoint, auth mutation or export rename.

6. Wire both Cookie platforms through capability/API/UI; explain credential subset and distinction between self authentication and creator/capture/playback. Record bounded new XHS source audit, never use request-ID fallback as identity proof. Remaining work remains required.

7. Run focused affected tests plus Web/static/docs/locks and independent review/package audit. Record failures, exact counts, environment skips and NOT_RUN honestly; do not inherit0064 full-suite PASS. Bilingual commits, normal push/fetch equality, separate publication record.
