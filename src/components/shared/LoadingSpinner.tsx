interface LoadingSpinnerProps {
  message?: string;
}

export default function LoadingSpinner({ message = "Cargando..." }: LoadingSpinnerProps) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background">
      <div
        className="h-12 w-12 animate-spin rounded-full border-4 border-primary border-t-transparent"
        role="status"
        aria-label="loading"
      />
      <p className="text-muted-foreground">{message}</p>
    </div>
  );
}
