import { Typography } from 'antd';
import KnowledgeBasePanel from '../components/KnowledgeBasePanel';

const { Title } = Typography;

export default function KnowledgeBasePage() {
  return (
    <div>
      <Title level={3} style={{ margin: 0, marginBottom: 16 }}>知识库</Title>
      <KnowledgeBasePanel />
    </div>
  );
}
