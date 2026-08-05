import { Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
import { Layout, Menu, Spin, Button, Dropdown } from "antd";
import { ShopOutlined, DashboardOutlined, LogoutOutlined, UserOutlined, SearchOutlined, PictureOutlined, BgColorsOutlined, CommentOutlined, EditOutlined, EnvironmentOutlined, ShoppingCartOutlined, VideoCameraOutlined } from "@ant-design/icons";
import { lazy, Suspense, useEffect, useState } from "react";
import { useAuthStore } from "./store/auth";
import { getMe } from "./services/auth";

const LoginPage = lazy(() => import("./pages/LoginPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const MerchantsPage = lazy(() => import("./pages/MerchantsPage"));
const ProfileIndexPage = lazy(() => import("./pages/ProfileIndexPage"));
const ProfileEditorPage = lazy(() => import("./pages/ProfileEditorPage"));
const CrawlJobsPage = lazy(() => import("./pages/CrawlJobsPage"));
const SubscriptionsPage = lazy(() => import("./pages/SubscriptionsPage"));
const MerchantDetailPage = lazy(() => import("./pages/MerchantDetailPage"));
const DesignIndexPage = lazy(() => import("./pages/DesignIndexPage"));
const DesignEditorPage = lazy(() => import("./pages/DesignEditorPage"));
const ReputationIndexPage = lazy(() => import("./pages/ReputationIndexPage"));
const ReputationWorkbenchPage = lazy(() => import("./pages/ReputationWorkbenchPage"));
const StudioIndexPage = lazy(() => import("./pages/StudioIndexPage"));
const DistrictIndexPage = lazy(() => import("./pages/DistrictIndexPage"));
const DistrictDetailPage = lazy(() => import("./pages/DistrictDetailPage"));
const StudioEditorPage = lazy(() => import("./pages/StudioEditorPage"));
const DealIndexPage = lazy(() => import("./pages/DealIndexPage"));
const DealEditorPage = lazy(() => import("./pages/DealEditorPage"));
const LiveIndexPage = lazy(() => import("./pages/LiveIndexPage"));
const LiveEditorPage = lazy(() => import("./pages/LiveEditorPage"));

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
    { key: "/studio", icon: <EditOutlined />, label: "内容工坊" },
    { key: "/reputation", icon: <CommentOutlined />, label: "口碑管理" },
    { key: "/district", icon: <EnvironmentOutlined />, label: "商圈分析" },
    { key: "/deals", icon: <ShoppingCartOutlined />, label: "团购工坊" },
    { key: "/live", icon: <VideoCameraOutlined />, label: "直播工坊" },
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
  }, [setAuth, token, user]);

  if (loading)
    return (
      <div style={{ minHeight: "100vh", display: "flex", justifyContent: "center", alignItems: "center" }}>
        <Spin size="large" />
      </div>
    );

  return (
    <Suspense
      fallback={
        <div style={{ minHeight: "100vh", display: "flex", justifyContent: "center", alignItems: "center" }}>
          <Spin size="large" />
        </div>
      }
    >
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
        path="/studio"
        element={
          <ProtectedRoute>
            <AppLayout>
              <StudioIndexPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/studio/:id"
        element={
          <ProtectedRoute>
            <AppLayout>
              <StudioEditorPage />
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
        path="/district"
        element={
          <ProtectedRoute>
            <AppLayout>
              <DistrictIndexPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/district/:shop_id"
        element={
          <ProtectedRoute>
            <AppLayout>
              <DistrictDetailPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/deals"
        element={
          <ProtectedRoute>
            <AppLayout>
              <DealIndexPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/deals/:id"
        element={
          <ProtectedRoute>
            <AppLayout>
              <DealEditorPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/live"
        element={
          <ProtectedRoute>
            <AppLayout>
              <LiveIndexPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/live/:id"
        element={
          <ProtectedRoute>
            <AppLayout>
              <LiveEditorPage />
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
    </Suspense>
  );
}








