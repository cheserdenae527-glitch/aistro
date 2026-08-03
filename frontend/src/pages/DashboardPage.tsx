import { Button, Typography } from "antd";
import { LogoutOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/auth";

const { Title, Text } = Typography;

export default function DashboardPage() {
 const user = useAuthStore((s) => s.user);
 const logout = useAuthStore((s) => s.logout);
 const navigate = useNavigate();

 const handleLogout = () => {
   logout();
   navigate("/login");
 };

 return (
   <div style={{ padding: 48 }}>
     <div
       style={{
         display: "flex",
         justifyContent: "space-between",
         alignItems: "center",
         marginBottom: 32,
       }}
     >
       <div>
         <Title level={2}>AiRestro 运营工作台</Title>
         <Text type="secondary">欢迎回来，{user?.name ?? "用户"}</Text>
       </div>
       <Button icon={<LogoutOutlined />} onClick={handleLogout}>
         退出登录
       </Button>
     </div>
     <div
       style={{
         display: "grid",
         gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
         gap: 16,
       }}
     >
       <div
         style={{
           background: "#fff",
           borderRadius: 8,
           padding: 24,
           border: "1px solid #f0f0f0",
         }}
       >
         <Text type="secondary">M1 完成</Text>
         <br />
         <Text strong>项目骨架已就绪</Text>
       </div>
     </div>
   </div>
 );
}
