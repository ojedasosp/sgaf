from flask import Flask, jsonify


def create_app():
    app = Flask(__name__)

    # Register blueprints
    from app.routes.health import health_bp

    app.register_blueprint(health_bp)

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


if __name__ == "__main__":
    import os

    app = create_app()
    try:
        port = int(os.environ.get("FLASK_PORT", "5000"))
    except ValueError:
        app.logger.warning("Invalid FLASK_PORT env var, falling back to 5000")
        port = 5000
    app.run(host="127.0.0.1", port=port)
