# Single-instance: предотвращение дублей ботов

## Инвариант

Каждый бот chatcore должен работать ровно в одном экземпляре под одним systemd-менеджером.

## Канон менеджеров

| Бот | Менеджер | Юнит |
|-----|----------|------|
| chat-davidkey, chat-ifs, chat-lukehawkins, chat-marni, chat-sigma, chat-socialself, chat-acharya-das, chat-vishvanath, chat-mentalist | user (`systemctl --user`) | `~/.config/systemd/user/<svc>.service` |
| chat-jacobs | system (`systemctl`) | `/etc/systemd/system/<svc>.service` |

Исключения (system-level): jacobs, mentalist работают под system-юнитом и не мигрируются.

## Три слоя защиты

### 1. Шаблон деплоя (chatcore/templates/deploy.yml)

При каждом деплое guard-шаг гасит одноимённый system-юнит, если он существует:

```yaml
sudo -n systemctl stop {{ SERVICE_NAME }} 2>/dev/null || true
sudo -n systemctl disable {{ SERVICE_NAME }} 2>/dev/null || true
systemctl --user daemon-reload
systemctl --user restart {{ SERVICE_NAME }}
```

### 2. Код chatcore (flock + Conflict-watchdog)

- **flock**: при старте `run()` берёт эксклюзивный лок на `<db_path>.lock`.
  Второй инстанс с тем же CWD мгновенно падает с CRITICAL-логом.
  Отключить аварийно: `SINGLE_INSTANCE_LOCK=0`.
- **Conflict-watchdog**: ≥5 ошибок `telegram.error.Conflict` подряд в окне 60 с →
  `os._exit(78)`. Конфликт становится видимым в `systemctl status` (flapping),
  вместо тихого воровства апдейтов.

### 3. Скрипт-аудит (scripts/check_single_instance.sh)

Проверяет три инварианта:
1. Один ExecStart не встречается в обоих менеджерах одновременно.
2. По каждому ExecStart не более одного процесса.
3. Нет строк `409 Conflict` в journald за последние 10 минут.

## Запуск аудита вручную

```bash
~/projects/chat/scripts/check_single_instance.sh
```

Вывод `OK: N ботов, дублей нет.` — всё чисто.
При FAIL — описание проблемы + exit 1.

## Установка таймера (один раз на VPS)

```bash
cp ~/projects/chat/scripts/systemd/check-single-instance.{service,timer} \
   ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now check-single-instance.timer
```

Проверить: `systemctl --user list-timers check-single-instance.timer`

При сбое аудита юнит остаётся в состоянии failed — виден в `systemctl --user --failed`.

## Откат версии chatcore

Если flock мешает: `SINGLE_INSTANCE_LOCK=0` в `.env` бота.
Откат пина: изменить `chatcore @ git+...@v0.1.3` → `@v0.1.2` в `requirements.txt` + redeploy.
