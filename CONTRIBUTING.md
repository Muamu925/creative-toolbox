# Contributing / 参与贡献

谢谢你试用创作工具箱。最有帮助的贡献，是描述一个真实工作流中遇到的问题。

Thanks for trying Creative Toolbox. A reproducible problem from a real workflow is a useful place to start.

## 问题与需求 / Issues and suggestions

使用仓库的问题模板，提供系统、工具箱版本、操作步骤、预期和实际结果。测试保存功能时请使用可丢弃文件；不要上传真实客户工程、个人目录内容或包含密钥的日志。需求请描述要完成的任务与现在遇到的阻力。

Use the issue templates with your OS, app version, steps, expected result, and actual result. Use disposable files for save tests. Do not attach client projects, secrets, or private material. Feature suggestions should explain the task and current friction.

## 开发流程 / Development

- Python 3.12+; install `requirements.txt` in a virtual environment.
- Run `python -m unittest discover -v` before submitting a behavioral change.
- Keep automatic-save changes separate from utility features; preserve observation mode on startup.
- Test platform-specific behavior on the actual OS, and clearly distinguish simulated tests from real-app verification.
- Describe the problem, resulting behavior, validation, and any remaining limitation in your pull request.
- Discuss substantial features in an issue before starting a large implementation.

Windows/macOS packages are built separately in GitHub Actions. See [development notes](docs/DEVELOPMENT.md) and the [roadmap](docs/FEATURE_ROADMAP.md).
