**English** | [中文](goal.zh.md)

# Goal

Deliver the requested paste-Cookie login workflow: the operator supplies a browser Cookie header, the service verifies authenticated remote data, and only a successful candidate becomes the privately stored credential used by later capture. Failure must preserve existing working credentials. The seven-platform login/subscription/capture/archive/local Emby/Jellyfin output goal remains unchanged.

Baseline: `68c4004`. Previous goal turn is progress: implemented and published 0057, with final regression and fresh-fetch equality. This execution addresses the explicitly accepted Cookie requirement rather than reclassifying the failed production canary.

Source audit supports bounded self-account verification for Bili, XHS, WB and Zhihu. Locked DY/Tieba pong only tests local markers; KS result-only GraphQL lacks an authenticated-versus-anonymous discriminator. Those three remain required, but must report unavailable until reliable remote evidence is implemented. No synthetic test grants live qualification.
