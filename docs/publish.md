# Публикация metagodlike на GitHub

1. Откройте [создание репозитория на GitHub](https://github.com/new?name=metagodlike) и выберите свой аккаунт. Если приёмная комиссия должна открыть ссылку без приглашения, выберите **Public**. Оставьте репозиторий пустым при создании, чтобы первый коммит пришёл из локального проекта.
2. Откройте PowerShell в папке `metagodlike` рядом с корневым README. Если начали с ZIP, сначала извлеките папку и выполните `git init -b main`.
3. Задайте имя и почту для Git-коммитов в этом репозитории. Почту можно взять из настроек аккаунта GitHub, включая вариант `noreply`.

```powershell
git config user.name "YOUR NAME"
git config user.email "YOUR EMAIL"
git add .
git status --short
git commit -m "Initial metagodlike project"
```

4. Скопируйте HTTPS-адрес нового репозитория и подставьте его в первую команду.

```powershell
git remote add origin https://github.com/YOUR-USERNAME/metagodlike.git
git push -u origin main
```

После отправки GitHub отобразит корневой README, а во вкладке **Actions** появится запуск проверок. Для заявки скопируйте ссылку на страницу репозитория. Откройте её в приватном окне браузера, чтобы убедиться, что README и скриншоты видны человеку без доступа к вашему аккаунту. Инструкция по запуску сайта находится в [README](../README.md#quick-start).

[Инструкция GitHub по загрузке локального проекта](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)
