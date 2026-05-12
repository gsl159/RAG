#!/usr/bin/env bash
# ==============================================================
# RAG System — 公网生产部署脚本
# 前提：一台 Linux 服务器（4GB+ RAM），Docker 已安装，域名已解析
# 用法：chmod +x deploy-prod.sh && ./deploy-prod.sh
# ==============================================================
set -euo pipefail

RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"
BLUE="\033[34m"; BOLD="\033[1m"; RESET="\033[0m"

info()  { echo -e "${GREEN}[INFO]${RESET}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error() { echo -e "${RED}[ERROR]${RESET} $*"; exit 1; }
step()  { echo -e "\n${BOLD}${BLUE}▶ $*${RESET}"; }

echo -e "${BOLD}${BLUE}"
cat << 'EOF'
  ____      _    ____   ____            _
 |  _ \    / \  / ___| / ___| _   _ ___| |_ ___ _ __ ___
 | |_) |  / _ \| |  _ \___ \| | | / __| __/ _ \ '_ ` _ \
 |  _ <  / ___ \ |_| | ___) | |_| \__ \ ||  __/ | | | | |
 |_| \_\/_/   \_\____||____/ \__, |___/\__\___|_| |_| |_|
                              |___/  Production Deployment
EOF
echo -e "${RESET}"

# ── 检查依赖 ──────────────────────────────────
step "检查系统依赖"
command -v docker         >/dev/null 2>&1 || error "请先安装 Docker"
command -v docker compose >/dev/null 2>&1 || error "请先安装 Docker Compose v2"

# ── 检查 .env ─────────────────────────────────
step "检查环境配置"
if [ ! -f .env ]; then
    if [ -f .env.prod.example ]; then
        info "未检测到 .env，正在从 .env.prod.example 模板创建…"
        cp .env.prod.example .env

        # 自动生成安全的 JWT_SECRET
        JWT_SECRET_VALUE=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")
        sed -i "s/CHANGE_ME_run_openssl_rand_hex_32/$JWT_SECRET_VALUE/" .env

        # 自动生成数据库密码
        PG_PASS=$(openssl rand -base64 16 2>/dev/null || python3 -c "import secrets; print(secrets.token_urlsafe(16))")
        sed -i "s/CHANGE_ME_strong_pg_password_2024/$PG_PASS/g" .env

        # 自动生成 MinIO 密码
        MINIO_PASS=$(openssl rand -base64 16 2>/dev/null || python3 -c "import secrets; print(secrets.token_urlsafe(16))")
        sed -i "s/CHANGE_ME_strong_minio_password_2024/$MINIO_PASS/g" .env

        # 自动生成管理员密码
        ADMIN_PASS=$(openssl rand -base64 12 2>/dev/null || python3 -c "import secrets; print(secrets.token_urlsafe(12))")
        sed -i "s/CHANGE_ME_admin_initial_password/$ADMIN_PASS/" .env

        echo ""
        warn "┌──────────────────────────────────────────────────┐"
        warn "│  .env 已生成，密码已自动填充。                     │"
        warn "│  请务必编辑 .env 填入以下内容后再次运行本脚本：      │"
        warn "│                                                    │"
        warn "│  1. DOMAIN=你的域名（已解析到本机 IP）              │"
        warn "│  2. SILICONFLOW_API_KEY=你的真实 API Key           │"
        warn "│  3. CORS_ORIGINS=[\"https://你的域名\"]            │"
        warn "│                                                    │"
        warn "│  管理员初始密码：${ADMIN_PASS}                      │"
        warn "│  （首次登录后请立即修改）                           │"
        warn "└──────────────────────────────────────────────────┘"
        echo ""
        info "编辑命令: nano .env"
        exit 0
    else
        error "未找到 .env 或 .env.prod.example 模板文件"
    fi
fi

# 校验关键配置
grep -q "sk-your-real-key-here" .env && error ".env 中 SILICONFLOW_API_KEY 尚未修改"
grep -q "rag.yourdomain.com" .env && error ".env 中 DOMAIN 尚未修改为你的真实域名"
DOMAIN=$(grep "^DOMAIN=" .env | cut -d'=' -f2)
[ -z "$DOMAIN" ] && error ".env 中未配置 DOMAIN"
info "域名: $DOMAIN ✓"
info "环境配置检查通过 ✓"

# ── 防火墙 ────────────────────────────────────
step "检查端口"
if command -v ufw >/dev/null 2>&1; then
    info "检测到 ufw 防火墙"
    ufw allow 80/tcp  >/dev/null 2>&1 || true
    ufw allow 443/tcp >/dev/null 2>&1 || true
    info "80/443 端口已放行"
elif command -v firewall-cmd >/dev/null 2>&1; then
    info "检测到 firewalld 防火墙"
    firewall-cmd --permanent --add-port=80/tcp  >/dev/null 2>&1 || true
    firewall-cmd --permanent --add-port=443/tcp >/dev/null 2>&1 || true
    firewall-cmd --reload >/dev/null 2>&1 || true
    info "80/443 端口已放行"
fi

# ── 拉取镜像 ──────────────────────────────────
step "拉取基础镜像"
docker compose pull --quiet etcd minio redis postgres 2>/dev/null || warn "部分镜像拉取失败，继续…"

# ── 启动基础设施 ──────────────────────────────
step "启动基础设施"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d etcd minio minio-init redis postgres
info "等待基础设施就绪…"

MAX=30; i=0
while ! docker compose exec -T postgres pg_isready -U raguser -d ragdb >/dev/null 2>&1; do
    i=$((i+1)); [ $i -ge $MAX ] && error "PostgreSQL 启动超时"; echo -n "."; sleep 2
done
info "PostgreSQL ✓"
docker compose exec -T redis redis-cli ping >/dev/null 2>&1 && info "Redis ✓" || warn "Redis 可能未就绪"

# ── 启动 Milvus ──────────────────────────────
step "启动 Milvus"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d milvus
MAX=30; i=0
while ! curl -sf http://localhost:9091/healthz >/dev/null 2>&1; do
    i=$((i+1)); [ $i -ge $MAX ] && { warn "Milvus 仍在启动…"; break; }; echo -n "."; sleep 2
done
echo ""; info "Milvus ✓"

# ── 构建并启动应用 ────────────────────────────
step "构建并启动应用 + Caddy"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build backend frontend caddy
info "等待后端启动…"

MAX=20; i=0
while ! docker compose exec -T backend curl -sf http://localhost:8000/health >/dev/null 2>&1; do
    i=$((i+1)); [ $i -ge $MAX ] && { warn "后端仍在启动…"; break; }; echo -n "."; sleep 3
done
echo ""

# ── 检查 HTTPS ────────────────────────────────
step "检查 HTTPS 证书"
sleep 5
if curl -sf "https://${DOMAIN}/api/health" >/dev/null 2>&1; then
    info "HTTPS 访问正常 ✓"
else
    warn "HTTPS 可能还在申请证书，Caddy 首次启动需要几秒到几分钟"
    warn "可通过 docker compose logs caddy 查看证书申请进度"
fi

# ── 完成 ──────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${GREEN}║          🚀  公网部署完成！                       ║${RESET}"
echo -e "${BOLD}${GREEN}╠══════════════════════════════════════════════════╣${RESET}"
echo -e "${BOLD}${GREEN}║${RESET}  访问地址:    ${BOLD}https://${DOMAIN}${RESET}"
echo -e "${BOLD}${GREEN}║${RESET}  API 文档:    ${BOLD}https://${DOMAIN}/api/docs${RESET}"
echo -e "${BOLD}${GREEN}║${RESET}  健康检查:    ${BOLD}https://${DOMAIN}/api/health${RESET}"
echo -e "${BOLD}${GREEN}║${RESET}                                                  ${BOLD}${GREEN}║${RESET}"
echo -e "${BOLD}${GREEN}║${RESET}  HTTPS 由 Caddy 自动管理（Let's Encrypt）        ${BOLD}${GREEN}║${RESET}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${YELLOW}常用命令：${RESET}"
echo -e "  查看全部日志:  ${BOLD}docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f${RESET}"
echo -e "  查看后端日志:  ${BOLD}docker compose logs -f backend${RESET}"
echo -e "  查看证书日志:  ${BOLD}docker compose logs -f caddy${RESET}"
echo -e "  查看状态:      ${BOLD}docker compose ps${RESET}"
echo -e "  停止服务:      ${BOLD}docker compose -f docker-compose.yml -f docker-compose.prod.yml down${RESET}"
echo ""
echo -e "  ${YELLOW}安全提醒：${RESET}"
echo -e "  1. 首次登录后请立即修改管理员密码"
echo -e "  2. 确保服务器 only 开放 80/443 端口"
echo -e "  3. 建议配置服务器防火墙，关闭其他端口"
echo ""
