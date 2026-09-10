# 数据库迁移脚本

按数字顺序执行即可：

```bash
mysql -u root -p your_database < 001_init.sql
```

后续新增迁移文件请按 `002_xxx.sql`、`003_xxx.sql` 递增命名。
