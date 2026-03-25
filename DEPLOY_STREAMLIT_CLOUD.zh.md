# 使用 GitHub + Streamlit Community Cloud 部署（持续可访问）

本文说明如何把本应用部署到 [Streamlit Community Cloud](https://streamlit.io/cloud)（免费层可用，需 GitHub 账号）。

## 1. 准备仓库内容

**建议单独建一个 Git 仓库**，只包含本应用需要的文件（不要把整桌面的无关项目一并推送）：

| 路径 | 说明 |
|------|------|
| `app.py` | 入口 |
| `src/` | 业务代码 |
| `requirements.txt` | Python 依赖 |
| `runtime.txt` | Python 版本（本仓库已指定 3.11） |
| `.streamlit/config.toml` | Streamlit 配置（可选） |
| `.gitignore` | 忽略 `.cache/`、虚拟环境等 |

若你当前目录里还有 `asin-dashboard/`、`claude test/` 等，**不要**把含密钥的 `.env` 推送到 GitHub。

## 2. 创建 GitHub 仓库并推送

```bash
cd "你的项目根目录"
git init
git add app.py src requirements.txt runtime.txt .streamlit .gitignore README.md DEPLOY_STREAMLIT_CLOUD.zh.md
git commit -m "Streamlit US product search app"
git branch -M main
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

## 3. 在 Streamlit Cloud 上部署

1. 打开 [share.streamlit.io](https://share.streamlit.io) 并登录（用 GitHub 授权）。
2. **New app** → 选择你的仓库与分支（如 `main`）。
3. **Main file path** 填：`app.py`
4. （若应用放在子目录）在高级设置里把 **App root** 指到该子目录，Main file 仍为相对路径，如 `app.py`。
5. 点击 **Deploy**。

部署成功后你会得到形如 `https://<别名>.streamlit.app` 的公网地址，**持续在线**（除非超出免费额度或服务维护）。

## 4. 部署后注意事项

- **出站抓取**：云端机房的 IP 与家里不同，部分电商站可能拒绝或返回验证码，搜索/抓取效果可能与本地不一致属正常现象。
- **缓存**：`.cache/` 已在 `.gitignore` 中；云端实例重启后缓存会清空。
- **机密**：本应用当前无需 API Key；若以后加 Key，请用 Streamlit Cloud 的 **Secrets**（勿写入仓库）。

## 5. 常见问题

- **依赖安装失败**：确认 `requirements.txt` 与 `runtime.txt` 中的 Python 版本匹配（本仓库锁为 3.11）。
- **无法访问**：在 Cloud 控制台查看 **Logs**，确认 `app.py` 路径与分支正确。
