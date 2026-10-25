import { useAuth } from "@/lib/auth/AuthContext";

export function SessionExpiredPage() {
  const { signIn } = useAuth();

  return (
    <div className="card-page">
      <div className="card">
        <h1>Sesión caducada</h1>
        <p>
          Tu sesión ha expirado. Por favor, inicia sesión nuevamente para continuar.
        </p>
        <button className="btn-primary" onClick={() => signIn("/")}>
          Iniciar sesión
        </button>
      </div>
    </div>
  );
}
