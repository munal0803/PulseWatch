export default function StatusBadge({ status }) {
  if (status === "up") {
    return <span className="badge badge-up">UP</span>;
  }
  if (status === "down") {
    return <span className="badge badge-down">DOWN</span>;
  }
  return <span className="badge badge-pending">PENDING</span>;
}
