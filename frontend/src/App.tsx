import { Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
import { Layout, Menu, Spin, Button, Dropdown } from "antd";
import { ShopOutlined, DashboardOutlined, LogoutOutlined, UserOutlined, SearchOutlined, PictureOutlined, BgColorsOutlined, CommentOutlined } from "@ant-design/icons";
import { useEffect, useState } from "react";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import MerchantsPage from "./pages/MerchantsPage";
import ProfileIndexPage from "./pages/ProfileIndexPage";
import ProfileEditorPage from "./pages/ProfileEditorPage";
import CrawlJobsPage from "./pages/CrawlJobsPage";
import SubscriptionsPage from "./pages/SubscriptionsPage";
import MerchantDetailPage from "./pages/MerchantDetailPage";
import DesignIndexPage from "./pages/DesignIndexPage";
import DesignEditorPage from "./pages/DesignEditorPage";
import ReputationIndexPage from "./pages/ReputationIndexPage";
import ReputationWorkbenchPage from "./pages/ReputationWorkbenchPage";
import { useAuthStore } from "./store/auth";
import { getMe } from "./services/auth";

const { Header, Content } = Layout;

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function AppLayout({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const menuItems = [
    { key: "/", icon: <DashboardOutlined />, label: "总看板" },
    { key: "/merchants", icon: <ShopOutlined />, label: "商家管理" },
    { key: "/crawl", icon: <SearchOutlined />, label: "爬虫管理" },
    { key: "/profile", icon: <PictureOutlined />, label: "账号装修" },
    { key: "/design", icon: <BgColorsOutlined />, label: "视觉设计" },
    { key: "/reputation", icon: <CommentOutlined />, label: "口碑管理" },
    { key: "/subscriptions", icon: <UserOutlined />, label: "博主订阅" },
  ];

  const selectedKey =
    menuItems.find(
      (item) =>
        location.pathname === item.key ||
        location.pathname.startsWith(`${item.key}/`)
    )?.key || location.pathname;

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header style={{ display: "flex", alignItems: "center", padding: "0 24px" }}>
        <div style={{ color: "#fff", fontSize: 18, fontWeight: "bold", marginRight: 40 }}>
          AiRestro
        </div>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ flex: 1, minWidth: 0 }}
        />
        <Dropdown
          menu={{
            items: [
              { key: "logout", icon: <LogoutOutlined />, label: "退出登录", onClick: handleLogout },
            ],
          }}
        >
          <Button type="text" style={{ color: "#fff" }} icon={<UserOutlined />}>
            {user?.name || "用户"}
          </Button>
        </Dropdown>
      </Header>
      <Content style={{ padding: 24, background: "#f5f5f5" }}>
        {children}
      </Content>
    </Layout>
  );
}

export default function App() {
  const [loading, setLoading] = useState(true);
  const setAuth = useAuthStore((s) => s.setAuth);
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);

  useEffect(() => {
    if (token && !user) {
      getMe()
        .then((u) => setAuth(token, u))
        .catch(() => {})
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  if (loading)
    return (
      <div style={{ minHeight: "100vh", display: "flex", justifyContent: "center", alignItems: "center" }}>
        <Spin size="large" />
      </div>
    );

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <AppLayout>
              <DashboardPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/merchants"
        element={
          <ProtectedRoute>
            <AppLayout>
              <MerchantsPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/subscriptions"
        element={
          <ProtectedRoute>
            <AppLayout>
              <SubscriptionsPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/crawl"
        element={
          <ProtectedRoute>
            <AppLayout>
              <CrawlJobsPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/merchants/:id"
        element={
          <ProtectedRoute>
            <AppLayout>
              <MerchantDetailPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/profile"
        element={
          <ProtectedRoute>
            <AppLayout>
              <ProfileIndexPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/design"
        element={
          <ProtectedRoute>
            <AppLayout>
              <DesignIndexPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/design/:id"
        element={
          <ProtectedRoute>
            <AppLayout>
              <DesignEditorPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/reputation"
        element={
          <ProtectedRoute>
            <AppLayout>
              <ReputationIndexPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/reputation/:shop_id"
        element={
          <ProtectedRoute>
            <AppLayout>
              <ReputationWorkbenchPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/shops/:shop_id/profile/:platform"
        element={
          <ProtectedRoute>
            <AppLayout>
              <ProfileEditorPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}






