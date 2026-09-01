# 模块目录

以后每个功能一个文件夹。底座会扫描这里的 `manifest.yaml`，列到网页「模块」页和侧栏。

已有模块：`portal`（网站入口）。

## 以后怎么加

```
modules/
  功能名/
    manifest.yaml    模块说明（底座靠它发现你）
    ...              该功能自己的页面、接口、表
```

`manifest.yaml` 最少写：

```yaml
id: portal
name: 网站入口
description: 收藏常用网站
version: 0.1.0
```
