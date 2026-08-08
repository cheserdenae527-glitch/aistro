import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import App from "./App";
import ErrorBoundary from "./components/ErrorBoundary";
import "./styles/app.css";

const theme = {
  token: {
    colorPrimary: "#050505",
    colorInfo: "#050505",
    colorSuccess: "#178A54",
    colorWarning: "#D97706",
    colorError: "#E61919",
    borderRadius: 0,
    colorBgLayout: "#F4F4F0",
    colorBgContainer: "#F4F4F0",
    colorBgElevated: "#F4F4F0",
    colorBorder: "#050505",
    colorText: "#050505",
    colorTextHeading: "#050505",
    fontFamily:
      '"Inter", "Segoe UI", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif',
  },
  components: {
    Layout: {
      siderBg: "#F4F4F0",
      headerBg: "#F4F4F0",
      bodyBg: "#F4F4F0",
    },
    Menu: {
      itemBg: "transparent",
      itemColor: "#050505",
      itemSelectedColor: "#050505",
      itemHoverBg: "transparent",
      itemSelectedBg: "transparent",
      itemBorderRadius: 0,
    },
    Card: {
      borderRadiusLG: 0,
    },
    Table: {
      headerBg: "#050505",
      headerColor: "#F4F4F0",
      rowHoverBg: "#050505",
    },
    Button: {
      primaryShadow: "none",
      defaultShadow: "none",
    },
    Input: {
      activeShadow: "none",
    },
    Modal: {
      contentBg: "#F4F4F0",
    },
  },
};

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <ConfigProvider locale={zhCN} theme={theme}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ConfigProvider>
    </ErrorBoundary>
  </React.StrictMode>
);