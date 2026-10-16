#!/usr/bin/env bash
# 把生成的 RSS 和管理后台部署到 Cloudflare Pages 的两个独立项目：
#   RSS 项目：文件放在随机路径下（FEED_BASE_URL 的最后一段），根目录什么都没有，Folo 无需登录即可抓取
#   后台项目：整站由 Cloudflare Access 保护，只有你的邮箱能登录
# 需要的环境变量：CLOUDFLARE_API_TOKEN、CLOUDFLARE_ACCOUNT_ID、CF_FEEDS_PROJECT、CF_ADMIN_PROJECT、FEED_BASE_URL
set -euo pipefail

WRANGLER=(npx --yes wrangler@4.146.0)
FEED_PATH="${FEED_BASE_URL##*/}"
if [ -z "$FEED_PATH" ] || [ "$FEED_PATH" = "$FEED_BASE_URL" ]; then
  echo "FEED_BASE_URL 格式不对，应为 https://<项目>.pages.dev/<随机路径>"
  exit 1
fi
# 随机路径本身不是一个完整的 Secret，GitHub 不会自动打码，手动加上
echo "::add-mask::$FEED_PATH"

out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT

common_headers='  X-Robots-Tag: noindex, nofollow
  X-Content-Type-Options: nosniff
  Referrer-Policy: no-referrer'
robots='User-agent: *
Disallow: /'

# ---------- RSS ----------
mkdir -p "$out/feeds/$FEED_PATH"
cp bili_up_*.xml all.xml subscriptions.opml "$out/feeds/$FEED_PATH/"
printf '%s\n' "$robots" > "$out/feeds/robots.txt"
printf 'Not Found\n' > "$out/feeds/404.html"
cat > "$out/feeds/_headers" <<HEADERS
/*
$common_headers
  Cache-Control: public, max-age=300
HEADERS

# ---------- 管理后台 ----------
mkdir -p "$out/admin"
cp admin/index.html "$out/admin/index.html"
printf '%s\n' "$robots" > "$out/admin/robots.txt"
cat > "$out/admin/_headers" <<HEADERS
/*
$common_headers
  Content-Security-Policy: default-src 'none'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' https://cdn.jsdelivr.net; style-src 'unsafe-inline'; img-src https://*.hdslb.com data:; connect-src https://api.github.com; base-uri 'none'; form-action 'none'; object-src 'none'; frame-ancestors 'none'
  X-Frame-Options: DENY
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  Cache-Control: no-store
HEADERS

deploy() {
  local dir="$1" project="$2" log="$out/$2.log"
  # 项目不存在就创建（首次部署时）
  if ! "${WRANGLER[@]}" pages project list > "$log" 2>&1 || ! grep -qw -- "$project" "$log"; then
    "${WRANGLER[@]}" pages project create "$project" --production-branch main >> "$log" 2>&1 || true
  fi
  # 输出里会带项目地址，公开仓库期间不打印，失败时只打印打码后的末尾几行
  if ! "${WRANGLER[@]}" pages deploy "$dir" --project-name "$project" --branch main --commit-dirty=true >> "$log" 2>&1; then
    tail -n 20 "$log" | sed -e "s/$FEED_PATH/***/g" -e "s/$project/***/g"
    return 1
  fi
}

deploy "$out/feeds" "$CF_FEEDS_PROJECT"
echo "✅ RSS 已部署"
deploy "$out/admin" "$CF_ADMIN_PROJECT"
echo "✅ 管理后台已部署"
