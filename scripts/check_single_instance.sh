#!/usr/bin/env bash
# Аудит дублей инстансов ботов.
# Проверяет три инварианта:
#   1. Один ExecStart не встречается одновременно в system- и user-менеджере.
#   2. По каждому ExecStart+WorkingDirectory+Environment запущен не более
#      одного процесса — идентификация сверяется с реальными
#      /proc/<pid>/cwd и /proc/<pid>/environ, а не только с текстом
#      команды (юниты одного venv или одного интерпретатора с идентичным
#      ExecStart различаются рабочей директорией и/или объявленными
#      Environment=).
#   3. В journald за последние 10 минут нет строк «409 Conflict» по этому юниту.
#
# Выход: 0 = всё чисто; 1 = найден дубль.
# Запускать от имени rocky: /proc/<pid>/{cwd,environ} читаемы только для
# процессов того же UID — юниты, запущенные от другого пользователя (в т.ч.
# system-юниты без явного User=), корректно не проверяются.

set -euo pipefail

FAIL=0

# ── Сбор юнитов ──────────────────────────────────────────────────────────────

declare -A SYSTEM_EXEC SYSTEM_WORKDIR SYSTEM_ENV
declare -A USER_EXEC USER_WORKDIR USER_ENV

_loaded_units() {
    # $1 = "" для system, "--user" для user
    local flag="$1"
    systemctl $flag list-units --all --no-legend --plain --type=service 2>/dev/null \
        | awk '{print $1}' | sed 's/\.service$//'
}

_collect() {
    local dir="$1"
    local manager="$2"  # "system" или "user"
    local flag="$3"     # "" или "--user"
    [[ -d "$dir" ]] || return 0
    local loaded
    loaded=$'\n'"$(_loaded_units "$flag")"$'\n'
    for f in "$dir"/*.service; do
        [[ -f "$f" ]] || continue
        # Пропускаем бэкап-юниты (*.disabled-*)
        [[ "$f" == *".disabled-"* ]] && continue
        local name
        name=$(basename "$f" .service)
        # Пропускаем юниты, не загруженные systemd (файл на диске есть,
        # а в менеджере его нет — устаревший/неактуальный юнит).
        [[ "$loaded" == *$'\n'"$name"$'\n'* ]] || continue
        local exec_start workdir
        exec_start=$(grep -m1 '^ExecStart=' "$f" 2>/dev/null | cut -d= -f2- || true)
        [[ -z "$exec_start" ]] && continue
        exec_start="${exec_start/\%h/$HOME}"
        workdir=$(grep -m1 '^WorkingDirectory=' "$f" 2>/dev/null | cut -d= -f2- || true)
        workdir="${workdir/\%h/$HOME}"
        if [[ -z "$workdir" ]]; then
            # systemd.exec(5): дефолт — "/" для system, $HOME для user.
            [[ "$manager" == "system" ]] && workdir="/" || workdir="$HOME"
        fi
        # Все строки Environment=, склеены \x1f-разделителем (KEY=VALUE каждая).
        local env_lines
        env_lines=$(grep '^Environment=' "$f" 2>/dev/null | cut -d= -f2- | paste -sd $'\x1f' - || true)
        if [[ "$manager" == "system" ]]; then
            SYSTEM_EXEC["$name"]="$exec_start"
            SYSTEM_WORKDIR["$name"]="$workdir"
            SYSTEM_ENV["$name"]="$env_lines"
        else
            USER_EXEC["$name"]="$exec_start"
            USER_WORKDIR["$name"]="$workdir"
            USER_ENV["$name"]="$env_lines"
        fi
    done
}

_collect /etc/systemd/system system ""
_collect "${HOME}/.config/systemd/user" user "--user"

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

# ── Инвариант 2: один процесс на (ExecStart, WorkingDirectory, Environment) ──

_check_procs() {
    local name="$1" exec_start="$2" workdir="$3" env_lines="$4"

    local pids
    pids=$(pgrep -f -- "$exec_start" 2>/dev/null || true)
    [[ -z "$pids" ]] && return 0

    local -a expected_env=()
    if [[ -n "$env_lines" ]]; then
        IFS=$'\x1f' read -r -a expected_env <<< "$env_lines"
    fi

    local count=0 pid
    for pid in $pids; do
        local actual_cwd
        actual_cwd=$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)
        [[ -z "$actual_cwd" || "$actual_cwd" != "$workdir" ]] && continue

        local ok=1
        if [[ ${#expected_env[@]} -gt 0 ]]; then
            local actual_env
            actual_env=$(tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null || true)
            local kv
            for kv in "${expected_env[@]}"; do
                [[ -z "$kv" ]] && continue
                if ! grep -qxF "$kv" <<< "$actual_env"; then
                    ok=0
                    break
                fi
            done
        fi
        [[ "$ok" -eq 1 ]] && count=$((count + 1))
    done

    if [[ "$count" -gt 1 ]]; then
        echo "FAIL: $name: найдено $count процессов для $exec_start (cwd=$workdir)"
        FAIL=1
    fi
}

for name in "${!SYSTEM_EXEC[@]}"; do
    _check_procs "$name" "${SYSTEM_EXEC[$name]}" "${SYSTEM_WORKDIR[$name]}" "${SYSTEM_ENV[$name]}"
done
for name in "${!USER_EXEC[@]}"; do
    _check_procs "$name" "${USER_EXEC[$name]}" "${USER_WORKDIR[$name]}" "${USER_ENV[$name]}"
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
