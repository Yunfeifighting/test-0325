# 推送到 GitHub：`jiaxianh/sku_check`

目标仓库：<https://github.com/jiaxianh/sku_check>

## 前置条件

1. 安装 [Git for Windows](https://git-scm.com/download/win)（安装时勾选 **“Git from the command line”**）。
2. 关闭并重新打开终端（或 Cursor），确保 `git --version` 能运行。
3. 在 GitHub 该仓库页面确认仓库已创建（可为空）。

## 方式 A：PowerShell 脚本（推荐）

在 **本目录**（含 `app.py` 的文件夹）打开 PowerShell，执行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\push_sku_check.ps1
```

按提示在浏览器完成 GitHub 登录（若使用 HTTPS）。首次 push 若要求登录，可使用 **Personal Access Token** 代替密码。

## 方式 B：手动命令

在 `AI test` 目录下（仅添加本应用相关文件，避免把 `asin-dashboard`、`.cache` 等推上去）：

```powershell
cd "c:\Users\39483\Desktop\AI test"

git init
git branch -M main

git add app.py src requirements.txt runtime.txt .gitignore README.md DEPLOY_STREAMLIT_CLOUD.zh.md GITHUB_PUSH_SKU_CHECK.md push_sku_check.ps1 .streamlit/config.toml run.bat

git status
git commit -m "Initial: US product search Streamlit app"

git remote add origin https://github.com/jiaxianh/sku_check.git
git push -u origin main
```

若 `remote` 已存在，改用：

```powershell
git remote set-url origin https://github.com/jiaxianh/sku_check.git
git push -u origin main
```

## Streamlit Cloud 部署

推送成功后，在 [Streamlit Community Cloud](https://share.streamlit.io) 绑定该仓库，**Main file path** 填 `app.py`。详见 [DEPLOY_STREAMLIT_CLOUD.zh.md](DEPLOY_STREAMLIT_CLOUD.zh.md)。
