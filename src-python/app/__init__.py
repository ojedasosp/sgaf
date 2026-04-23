from flask import Flask, jsonify
from flask_cors import CORS


def create_app():
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Initialize database and run migrations
    from app.database import get_engine
    from migrations.runner import run_migrations

    try:
        engine = get_engine()
        run_migrations(engine)
    except RuntimeError as exc:
        app.logger.error("Database initialization failed: %s", exc)
        raise  # Propagate so Tauri detects the crash and shows error screen

    # Register blueprints
    from app.routes.assets import assets_bp
    from app.routes.audit import audit_bp
    from app.routes.auth import auth_bp
    from app.routes.config import config_bp
    from app.routes.depreciation import depreciation_bp
    from app.routes.health import health_bp
    from app.routes.maintenance import maintenance_bp
    from app.routes.photos import photos_bp
    from app.routes.reports import reports_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(depreciation_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(photos_bp)
    app.register_blueprint(reports_bp)

    # Global JSON error handler — never return HTML from Flask
    @app.errorhandler(Exception)
    def handle_exception(e):
        app.logger.exception("Unhandled error")
        return jsonify({"error": "INTERNAL_ERROR", "message": str(e)}), 500

    @app.errorhandler(404)
    def handle_404(e):
        return jsonify({"error": "NOT_FOUND", "message": "Endpoint not found"}), 404

    @app.errorhandler(405)
    def handle_405(e):
        return jsonify({"error": "METHOD_NOT_ALLOWED", "message": "Method not allowed"}), 405

    return app


if __name__ == "__main__":  # pragma: no cover
    import os

    app = create_app()
    try:
        port = int(os.environ.get("FLASK_PORT", "5000"))
    except ValueError:
        app.logger.warning("Invalid FLASK_PORT env var, falling back to 5000")
        port = 5000
    app.run(host="127.0.0.1", port=port)
