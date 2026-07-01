#!/bin/bash
# PyPI 镜像探测（国内优先，官方兜底）。供 Linux 安装脚本 source 使用。
#
# 用法（在已定义 PIP_ARGS 数组的脚本中）：
#   source "$SCRIPT_DIR/scripts/pypi_mirror.sh"
#   ensure_pypi_mirror_pip_args   # 仅当 PIP_ARGS 为空时写入 -i <mirror>

PYPI_MIRRORS=(
    "https://pypi.tuna.tsinghua.edu.cn/simple"
    "https://mirrors.aliyun.com/pypi/simple"
    "https://pypi.mirrors.ustc.edu.cn/simple"
    "https://mirrors.cloud.tencent.com/pypi/simple"
    "https://pypi.org/simple"
)

pypi_mirror_probe() {
    local url="$1"
    local code="000"

    if command -v curl >/dev/null 2>&1; then
        code="$(curl -fsSIL --max-time 3 -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || true)"
        [ -n "$code" ] || code="000"
    elif command -v wget >/dev/null 2>&1; then
        if wget --spider --timeout=3 --tries=1 "$url" >/dev/null 2>&1; then
            code="200"
        fi
    else
        return 1
    fi

    [[ "$code" =~ ^[2-4][0-9][0-9]$ ]]
}

pypi_mirror_select() {
    local url
    for url in "${PYPI_MIRRORS[@]}"; do
        if pypi_mirror_probe "$url"; then
            echo "PyPI 镜像可用: $url" >&2
            printf '%s\n' "$url"
            return 0
        fi
        echo "PyPI 镜像不可用: $url" >&2
    done
    echo "所有镜像探测失败，回退官方源 pypi.org" >&2
    printf '%s\n' "https://pypi.org/simple"
}

# 用户未传 --pip-arg 时，自动探测可用镜像并写入 PIP_ARGS（-i <url>）。
ensure_pypi_mirror_pip_args() {
    if [ "${#PIP_ARGS[@]}" -gt 0 ]; then
        return 0
    fi
    local mirror
    mirror="$(pypi_mirror_select)"
    PIP_ARGS=("-i" "$mirror")
}
