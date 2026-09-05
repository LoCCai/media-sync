[English](verification.md) | **中文**

# 验证记录

fresh fetch：HEAD/origin为`76165b0`、分歧0 0、工作区干净。锁定MediaCrawler d6f7c5bb906b6dac40ddf343ef9e26438a3de092及bili-sync-up dcb5bb73b56ac45b2525da14b389e185b0ea6dbd不变。只读源发现仅使用本地文件和公开GitHub/raw固定SHA文件，未请求目标平台或接触凭据。冻结计划时未跑新测试；0061结果为历史，不继承。

探索时PowerShell传入字面通配路径被rg拒绝，另有猜测subscriptions.py路径不存在；已列出真实文件并改读subscription_policy.py。均为不写数据的源发现错误，不是产品测试失败。后续逐项记录实际验证结果。
