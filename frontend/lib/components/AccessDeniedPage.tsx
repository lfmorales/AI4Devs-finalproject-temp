export interface AccessDeniedPageProps {
  /** Custom message (defaults to generic forbidden message) */
  message?: string;
}

export function AccessDeniedPage({ message }: AccessDeniedPageProps) {
  const displayMessage =
    message || "No tienes permiso para acceder a esta sección. Contacta al administrador si crees que es un error.";

  return (
    <div className="card-page">
      <div className="card">
        <h1>Acceso denegado</h1>
        <p>{displayMessage}</p>
        <a className="btn btn-primary" href="/">
          Volver al inicio
        </a>
      </div>
    </div>
  );
}
