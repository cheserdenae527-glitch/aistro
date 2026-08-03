import { useState } from "react";
import { Button, Card, Form, Input, message, Typography } from "antd";
import { MailOutlined, LockOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { login, register } from "../services/auth";
import { useAuthStore } from "../store/auth";

const { Title } = Typography;

export default function LoginPage() {
 const [loading, setLoading] = useState(false);
 const [isRegister, setIsRegister] = useState(false);
 const navigate = useNavigate();
 const setAuth = useAuthStore((s) => s.setAuth);

 const onFinish = async (values: {
   email: string;
   password: string;
   name?: string;
 }) => {
   setLoading(true);
   try {
     const data = isRegister
       ? await register(values.email, values.password, values.name!)
       : await login(values.email, values.password);
     setAuth(data.access_token, data.user);
     message.success(isRegister ? "注册成功" : "登录成功");
     navigate("/");
   } catch {
     message.error(isRegister ? "注册失败，请重试" : "邮箱或密码错误");
   } finally {
     setLoading(false);
   }
 };

 return (
   <div
     style={{
       minHeight: "100vh",
       display: "flex",
       justifyContent: "center",
       alignItems: "center",
       background: "#f0f2f5",
     }}
   >
     <Card style={{ width: 400 }}>
       <Title level={3} style={{ textAlign: "center", marginBottom: 24 }}>
         AiRestro
       </Title>
       <Form
         layout="vertical"
         onFinish={onFinish}
         autoComplete="off"
         requiredMark={false}
       >
         {isRegister && (
           <Form.Item
             label="姓名"
             name="name"
             rules={[{ required: true, message: "请输入姓名" }]}
           >
             <Input placeholder="您的姓名或团队名" />
           </Form.Item>
         )}
         <Form.Item
           label="邮箱"
           name="email"
           rules={[
             { required: true, type: "email", message: "请输入有效邮箱" },
           ]}
         >
           <Input prefix={<MailOutlined />} placeholder="your@email.com" />
         </Form.Item>
         <Form.Item
           label="密码"
           name="password"
           rules={[{ required: true, message: "请输入密码" }]}
         >
           <Input.Password prefix={<LockOutlined />} placeholder="密码" />
         </Form.Item>
         <Form.Item>
           <Button type="primary" htmlType="submit" block loading={loading}>
             {isRegister ? "注册" : "登录"}
           </Button>
         </Form.Item>
         <Form.Item style={{ textAlign: "center", marginBottom: 0 }}>
           <Button type="link" onClick={() => setIsRegister(!isRegister)}>
             {isRegister ? "已有账号？去登录" : "没有账号？去注册"}
           </Button>
         </Form.Item>
       </Form>
     </Card>
   </div>
 );
}
