# 学生社团管理系统

基于 Django 和 MySQL 的学生社团管理 Web 应用，使用 Django 模板、Bootstrap 和 jQuery 实现页面，使用 SimpleUI 提供后台管理界面。

## 功能

- 学生：学号注册与登录、修改密码、浏览和搜索社团、加入和退出社团、查看成员名单、报名和取消活动报名。
- 社长：管理成员、上传和删除宣传照片、提交活动申请、上传活动图片及 PDF / Word 申请材料、查看审批记录。
- 管理员：管理学生、社团、成员和活动，审批及批量审批活动。
- 首页：展示社团、学生及审批通过的活动数量。

## 业务规则

- 每名学生最多加入两个社团，后台添加成员和指定社长也受此限制。
- 社长身份统一由社团的 `president` 字段决定，设置社长时自动建立成员关系；转让后，原社长保留普通成员身份。
- 社长不能直接退出或被移除，需先转让职位。
- 成员人数与活动报名人数直接从关联记录计算，后台修改同样生效。
- 仅社团成员可以报名审批通过且尚未开始的活动；名额检查和创建报名在同一事务中完成并加行锁。
- 退出或被移出社团时，自动取消该社团的活动报名。
- 成员名单仅对该社团成员、社长及管理员开放；未公开活动仅社长及管理员可查看。
- 申请附件仅社长及管理员可通过权限校验后的下载接口访问。
- 修改数据的页面操作使用 POST 请求并校验 CSRF Token。

## 技术栈与环境要求

| 组件 | 版本 | 用途 |
| --- | --- | --- |
| Python | 3.12 | 运行环境 |
| Django | 6.0.3 | Web 框架 |
| MySQL Server | 8.0.11+ | 数据库与事务行锁 |
| django-simpleui | 2026.1.13 | 后台管理界面 |
| mysqlclient | 2.3.0 | MySQL 驱动 |
| Pillow | 13.0.0 | 图片校验 |
| python-dotenv | 1.2.4 | 读取环境配置 |

Python 版本兼容范围见 [Django 6.0 发布说明](https://docs.djangoproject.com/en/6.0/releases/6.0/)，数据库要求见 [Django 数据库文档](https://docs.djangoproject.com/en/6.0/ref/databases/)。

Bootstrap、jQuery、样式和字体已包含在 `management/static/`，无需安装 Node.js 或 npm。Word / PDF 附件仅作为文件保存，无需安装 Office 或文档解析服务。

## 安装与运行

下载或克隆仓库后，进入包含 `manage.py` 的项目根目录，执行以下步骤。

### 1. 创建环境并安装依赖

安装 [Miniforge](https://github.com/conda-forge/miniforge) 或其他 Conda 发行版，在支持 Conda 的终端中运行：

```shell
conda create -n shetuan python=3.12 pip --override-channels -c conda-forge -y
conda activate shetuan
python -m pip install -r requirements.txt
python -m pip check
```

MySQL Server 需要单独安装并启动，`mysqlclient` 只提供数据库驱动。

### 2. 配置环境变量

复制配置模板。在 PowerShell 中执行：

```powershell
Copy-Item .env.example .env
```

在 macOS / Linux 中执行：

```shell
cp .env.example .env
```

生成随机密钥并写入 `.env`：

```shell
python -c "from dotenv import set_key; from django.core.management.utils import get_random_secret_key; set_key('.env', 'DJANGO_SECRET_KEY', get_random_secret_key())"
```

编辑 `.env` 中的数据库连接信息：

```dotenv
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DB_NAME=shetuan
DB_USER=shetuan
DB_PASSWORD=填写数据库密码
DB_HOST=127.0.0.1
DB_PORT=3306
```

保留生成的 `DJANGO_SECRET_KEY`。`.env` 已被 `.gitignore` 排除，不能提交到 Git；生产环境也可直接注入同名环境变量，它们优先于 `.env`。

### 3. 初始化数据库

使用有权限的 MySQL 账号创建数据库，并给应用账号授予该数据库的访问权限：

```sql
CREATE DATABASE shetuan
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

数据库已存在时无需重复创建。执行迁移并创建管理员：

```shell
python manage.py migrate
python manage.py createsuperuser
```

管理员创建需填写学号、姓名、邮箱和密码。社团、成员等数据可在后台添加。首次部署使用仓库内现有迁移，无需运行 `makemigrations`。

数据库导出文件不提交到仓库。新部署使用 Django 迁移；恢复旧数据库前应备份，并在恢复后执行迁移。

### 4. 启动服务

```shell
python manage.py check
python manage.py runserver
```

- 首页：[http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- 后台：[http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

`runserver` 用于开发调试，按 `Ctrl+C` 停止。

## 使用流程

### 学生

1. 注册并使用学号登录。
2. 在“全部社团”中按分类筛选或搜索，进入详情加入社团。
3. 在“我的社团”查看成员关系或退出社团。
4. 在活动中心或社团详情中查看活动，进入活动详情报名或取消报名。

### 社长

管理员在后台设置社团的 `president` 后，系统自动建立该学生的社团成员关系，无需手动维护角色字段。社长在“我的社团”中点击“管理”进入面板，维护宣传照片和成员、提交活动申请并查看审核记录。

### 管理员

在 `/admin/` 管理业务数据。成员可在“社团成员关系”中添加或删除；社团页面展示成员关系和计算后的人数。更换社长在社团编辑页完成。

## 文件上传

- 图片：JPEG、PNG、WebP、GIF，每张最多 5 MB，校验图片内容及扩展名。
- 附件：PDF、DOC、DOCX，每份最多 10 MB，校验文件头或 DOCX 容器结构。
- 每次最多提交 10 张图片和 10 份附件。
- 所有文件先校验，再在事务中创建记录；提交失败时回滚数据库并清理已写入的文件。
- 图片删除在数据库事务提交后清理对应文件。

上传内容保存到 `media/`，该目录不提交到 Git。备份或迁移系统时需同时保存数据库和上传文件。文件格式校验不替代恶意软件扫描。

## 测试

回归测试使用独立 MySQL 测试库，以验证真实行锁和并发行为。测试账号需拥有创建、删除测试数据库的权限，生产应用账号无需授予这些权限。

```shell
python manage.py test management --settings=Shetuan.settings_test
```

默认测试库为 `test_shetuan_regression`，可通过环境变量 `DB_TEST_NAME` 指定其他名称。测试会创建并销毁该测试库；不要将其设为业务数据库。生产账号权限受限时，应在独立开发数据库服务中运行测试。

测试覆盖权限与 CSRF、注册与密码校验、社长转让、成员上限、并发抢名额、上传限制及回滚、附件权限、模板渲染，以及数据库迁移与回退。

## 升级已有数据库

升级前备份数据库及 `media/`，然后运行：

```shell
python manage.py migrate
```

`0005_enforce_business_rules` 会移除冗余的人数计数和角色列，改为从成员、报名关系和 `president` 计算；保留成员及报名记录，并补齐缺失的社长成员关系。回退该迁移时会重新计算旧列。

如果旧数据包含参与人数小于 1、结束时间不晚于开始时间、学生加入超过两个社团，或无法确定唯一旧社长的情况，迁移会先报错中止。请修正旧数据后重试。

## 部署配置

生产环境设置 `DJANGO_DEBUG=False`，使用独立随机密钥、明确的域名列表和专用数据库账号。默认启用 HTTPS 跳转、安全 Cookie 和 HSTS。通过反向代理部署时，需按实际 HTTPS 终止方式配置 Django 的代理信任设置，避免跳转循环。

```shell
python manage.py check --deploy
python manage.py collectstatic --noinput
```

- 静态文件输出到 `staticfiles/`，由 Web 服务器提供。
- 公开媒体只允许 `media/club_photos/` 和 `media/activity_gallery/`；不要直接公开整个 `media/`，其中的 `activity_docs/` 必须通过应用下载接口访问。
- 普通页面拒绝 iframe 嵌入，SimpleUI 后台仅允许同源嵌入。
- `DJANGO_HSTS_SECONDS` 可调整 HSTS 时长。只有确认所有子域都使用 HTTPS 后，才设置 `DJANGO_HSTS_INCLUDE_SUBDOMAINS=True`；只有决定申请预加载后，才设置 `DJANGO_HSTS_PRELOAD=True`。默认不启用这两项，部署检查会保留对应提示。
- 若密钥或数据库凭据曾公开，应更换相关凭据；从源码移除不能撤销已经发生的泄露。

## 项目结构

```text
Shetuan/
├── manage.py
├── requirements.txt
├── .env.example                 # 配置模板，不包含实际凭据
├── Shetuan/                     # 设置、路由和安全中间件
├── management/
│   ├── models.py                # 数据模型与事务内业务规则
│   ├── forms.py                 # 注册、密码和活动表单校验
│   ├── validators.py            # 上传格式、大小和数量限制
│   ├── views.py                 # 页面、权限和 POST 操作
│   ├── signals.py               # 成员退出时取消报名及文件清理
│   ├── admin.py                 # 后台管理及审批
│   ├── migrations/              # 数据库迁移
│   ├── static/                  # 前端资源及默认活动图
│   └── tests.py                 # 权限、业务及并发回归测试
└── templates/management/        # 页面模板
```
