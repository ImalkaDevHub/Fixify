import Link from "next/link";

export default function NotFound() {
  return (
    <main className="page-content">
      <div className="empty-state">
        <h1>Page not found</h1>
        <p>The page you’re looking for doesn’t exist or may have moved.</p>
        <Link className="button" href="/">Back to overview</Link>
      </div>
    </main>
  );
}
