#!/usr/bin/env bash
# Аудит дублей инстансов ботов.
# Проверяет три инварианта:
#   1. Один ExecStart не встречается одновременно в system- и user-менеджере.
#   2. По каждому ExecStart запущен не более одного процесса.
#   3. В journald за последние 10 минут нет строк «409 Conflict» по этому юниту.
#
# Выход: 0 = всё чисто; 1 = найден дубль.
# Запускать от имени rocky (user-юниты видны только ему).

set -euo pipefail

FAIL=0

# ── Сбор юнитов ──────────────────────────────────────────────────────────────

declare -A SYSTEM_EXEC  # service_name -> ExecStart
declare -A USER_EXEC

_collect() {
    local dir="$1"
    local manager="$2"  # "system" или "user"
    [[ -d "$dir" ]] || return 0
    for f in "$dir"/*.service; do
        [[ -f "$f" ]] || continue
        # Пропускаем бэкап-юниты (*.disabled-*)
        [[ "$f" == *".disabled-"* ]] && continue
        local name
        name=$(basename "$f" .service)
        local exec_start
        exec_start=$(grep -m1 '^ExecStart=' "$f" 2>/dev/null | cut -d= -f2- || true)
        [[ -z "$exec_start" ]] && continue
        if [[ "$manager" == "system" ]]; then
            SYSTEM_EXEC["$name"]="$exec_start"
        else
            USER_EXEC["$name"]="$exec_start"
        fi
    done
}

_collect /etc/systemd/system system
_collect "${HOME}/.config/systemd/user" user

# ── Инвариант 1: один ExecStart — один менеджер ──────────────────────────────

for name in "${!USER_EXEC[@]}"; do
    user_exec="${USER_EXEC[$name]}"
    for sys_name in "${!SYSTEM_EXEC[@]}"; do
        if [[ "${SYSTEM_EXEC[$sys_name]}" == "$user_exec" ]]; then
            echo "FAIL: дубль ExecStart: user=$name, system=$sys_name -> $user_exec"
            FAIL=1
        fi
    done
done

# ── Инвариант 2: один процесс на ExecStart ───────────────────────────────────

_check_procs() {
    local name="$1"
    local exec_start="$2"
    # Берём путь до бинаря (первый токен) — он уникален для venv-ботов.
    # Если бинарь — общий интерпретатор (python3, bash и т.п.), пропускаем:
    # такой счёт всегда > 1 и не является признаком дубля.
    local binary
    binary=$(echo "$exec_start" | awk '{print $1}')
    # Пропускаем общие бинари и системные скрипты — только venv/project-пути уникальны.
    case "$binary" in
        /home/rocky/projects/*/\.venv/*)
            : ;;  # venv-бот — проверяем
        *)
            return 0  # общий интерпретатор или системный скрипт — пропускаем
            ;;
    esac
    local count
    count=$(pgrep -fc "$binary" 2>/dev/null || true)
    if [[ "$count" -gt 1 ]]; then
        echo "FAIL: $name: найдено $count процессов для $binary"
        FAIL=1
    fi
}

for name in "${!SYSTEM_EXEC[@]}"; do
    _check_procs "$name" "${SYSTEM_EXEC[$name]}"
done
for name in "${!USER_EXEC[@]}"; do
    _check_procs "$name" "${USER_EXEC[$name]}"
done

# ── Инвариант 3: нет 409 Conflict за последние 10 минут ──────────────────────

_check_409() {
    local name="$1"
    local flag="$2"  # "" для system, "--user" для user
    local count
    count=$(journalctl $flag -u "${name}.service" --since -10min --no-pager -q 2>/dev/null \
        | grep -c "409 Conflict" || true)
    if [[ "$count" -gt 0 ]]; then
        echo "FAIL: $name: $count строк «409 Conflict» за последние 10 мин"
        FAIL=1
    fi
}

for name in "${!SYSTEM_EXEC[@]}"; do
    _check_409 "$name" ""
done
for name in "${!USER_EXEC[@]}"; do
    _check_409 "$name" "--user"
done

# ── Итог ─────────────────────────────────────────────────────────────────────

TOTAL_SYSTEM=${#SYSTEM_EXEC[@]}
TOTAL_USER=${#USER_EXEC[@]}
TOTAL=$(( TOTAL_SYSTEM + TOTAL_USER ))

if [[ $FAIL -eq 0 ]]; then
    echo "OK: $TOTAL ботов (system: $TOTAL_SYSTEM, user: $TOTAL_USER), дублей нет."
    exit 0
else
    exit 1
fi
