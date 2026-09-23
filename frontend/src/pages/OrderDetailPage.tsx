import { useParams } from 'react-router-dom';
import OrderDetail from '../features/dispatcher/OrderDetail';

export default function OrderDetailPage() {
  const { orderId } = useParams<{ orderId: string }>();
  if (!orderId) return <div>Ordre non trouvé</div>;
  return <OrderDetail orderId={parseInt(orderId, 10)} />;
}
