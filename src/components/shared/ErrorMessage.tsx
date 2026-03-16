interface ErrorMessageProps {
  message: string;
  hint?: string;
}

export default function ErrorMessage({ message, hint }: ErrorMessageProps) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background p-8">
      <div className="max-w-md rounded-lg border border-destructive/20 bg-destructive/5 p-6 text-center">
        <h2 className="mb-2 text-lg font-semibold text-destructive">
          Error al iniciar SGAF
        </h2>
        <p className="text-sm text-muted-foreground">{message}</p>
        {hint && <p className="mt-3 text-xs text-muted-foreground">{hint}</p>}
      </div>
    </div>
  );
}
