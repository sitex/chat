# Цель
Переиспользуемый Python-пакет chatcore для быстрого создания Telegram-ботов с персоной, памятью диалога, LLM-каскадом (Claude/Grok/Ollama) и опциональной RAG на курсовом контенте. Ядро установится как зависимость в боты семейства (mentalist, mannix, jacobs, vishvanath, davidkey, ifs, socialself, acharya-das и др.).

## Критерии готовности
- [ ] chatcore работает как pip-пакет, все пиэхи-версии ботов импортируют из него без ошибок
- [ ] LLM-каскад достаточен: cliproxy → Grok → claude-cli → claude → ollama при недоступности предыдущих
- [ ] Memory (SQLite) сохраняет историю, видимость диалогов и настройки пользователя
- [ ] RAG готов для ботов с контентом (курсы, факты)
- [ ] Миграция основных ботов завершена: mentalist, jacobs, vishvanath, davidkey (mannix отложен, нетипичен)

## Политика ответов
- Водитель сам решает: обновление LLM-каскада, исправления memory/retrieval, миграция новых ботов, параметры scaffold, hot-reload data/, avatar-генерация, версионирование пакета.
- Эскалировать человеку: смена архитектуры ядра, удаление ботов, изменение интерфейса scaffold, merge PR с конфликтами, деплой на продакшн.

## Ограничения
- Python 3.10+, зависит от python-telegram-bot и anthropic SDK
- Пакет внутренний, не публичный (per README)
- Привязана к Telegram API (Bot API) и LLM-провайдерам (Anthropic, Grok через cliproxy, локальный Ollama)
- Scaffold требует data/persona.json, часто привязана к конкретным study-* репозиториям (для RAG)
