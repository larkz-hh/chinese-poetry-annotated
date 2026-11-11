# 贡献指南

[项目首页](README.md) · [构建与维护](docs/maintenance.md) · [内容审核与修订](docs/review.md)

欢迎提交数据纠错、改进建议、接入问题、文档修订和工具改进。不了解构建流程也可以通过 Issue 提供线索，无须先修改数据库。

## 选择反馈入口

提交前可先在 [已有 Issues](https://github.com/larkz-hh/chinese-poetry-annotated/issues) 中搜索相关作品或问题，已有讨论可直接补充。

| 反馈内容 | 入口 |
|---|---|
| 正文、译注、作者、分类或名句存在问题 | [数据纠错](https://github.com/larkz-hh/chinese-poetry-annotated/issues/new?template=01-data-correction.yml) |
| 数据库读取、搜索、构建或导出异常 | [接入与工具问题](https://github.com/larkz-hh/chinese-poetry-annotated/issues/new?template=02-bug-report.yml) |
| 新增数据、字段、分发格式或维护能力 | [改进建议](https://github.com/larkz-hh/chinese-poetry-annotated/issues/new?template=03-feature-request.yml) |

其他问题可以通过 [Issue 选择页](https://github.com/larkz-hh/chinese-poetry-annotated/issues/new/choose) 提交。

## 数据纠错需要的信息

请尽量提供以下内容，便于定位和核查：

- 作品题名与作者；如涉及作者资料，可直接提供作者姓名。
- 作品或作者 ID，以及问题字段、原有文字和具体位置。
- 发现问题的数据包及版本；版本可在对应 `manifest.json` 中查看 `data_version`。
- 建议修改的内容、理由及出处，如古籍版本、卷次、页码或可访问链接。

暂时无法给出完整改法或出处时，可以说明疑点与核查线索。不同版本、训读或解释可能并存，请说明所据版本；有依据的异文会结合版本记录处理。AI 输出可以作为线索，确定性修改仍需可核查的依据。

例如：

```text
作品：题名 / 作者
作品 ID：如已知请填写
数据包与版本：app-runtime / manifest 中的 data_version
问题字段：notes
当前内容：引用有问题的原条目
问题说明：指出具体错字、解释或格式问题
建议修改：给出建议，或注明需要进一步核查
参考依据：书名、版本、卷页或链接
```

每个 Issue 尽量围绕一个问题；同一原因影响多篇作品时，可在同一条中列出受影响记录。

## 提交 Pull Request

1. Fork 仓库并创建分支，每个 PR 聚焦一项修改。
2. 在 PR 中说明问题、修改结果及验证方式；已有 Issue 时关联其编号。
3. 数据修改提供记录 ID、前后内容和依据；文档、代码修改提供对应说明。
4. 根据改动执行必要检查，再提交 PR。

### 数据修改

数据由来源素材和显式修订记录构建生成。请优先提交可审阅的维护记录或构建工具修改，避免只修改发布用的 `poems.json` 或二进制数据库，导致下次重建丢失修订。

维护记录的职责见 [记录索引](docs/review.md#维护记录索引)。涉及正文、注释或名句时，须保持正文绑定、前后哈希及已有稳定 ID 的一致性；原始模型意见和历史修订记录应保留。注释约定见 [注释格式](docs/notes-format.md)，选句约定见 [名句维护](docs/famous-lines.md#维护与验证)。

不确定应修改哪个文件时，可以先提交纠错 Issue，由维护者协助落入修订记录。维护者按 [构建流程](docs/maintenance.md#常规重建) 生成并验证完整包与运行包。

### 代码与文档修改

代码保持与现有工具一致的风格。修改构建、查询或校验行为时，应验证实际受影响的路径；修复问题时按需要补充回归用例。

```powershell
python -X utf8 -m unittest discover -s scripts -p "test_*.py" -v
```

涉及数据构建时，可按维护指南在临时目录验证：

```powershell
python -X utf8 scripts/rebuild.py --app-only --check-only
```

上述操作均无需模型接口。仅修改文档时，检查链接、示例与实际结构是否一致即可，无须重建数据库。

## 来源与授权

贡献原创代码和原创文档时，沿用项目的 [MIT 许可证](LICENSE)。新增第三方数据或引用应注明来源、版本及已知授权条件，具体范围见 [数据来源与授权说明](docs/data-license.md)。

数据纠错经核查后进入修订记录，并随后续数据包更新发布；有依据的解释分歧会保留说明。
