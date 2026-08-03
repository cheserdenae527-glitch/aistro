# D3 Findings

- 后端菜单接口已就绪（designService.listMenus/createMenu/updateMenu/renderMenu）。
- 素材列表接口默认排除派生候选，D3 ItemPicker 只取 asset_type=dish 且 active。
- 色板复用 GET /color-schemes（profiles 服务已有封装）。
