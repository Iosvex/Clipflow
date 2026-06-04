print("✅✅✅ HELLO FROM PYTHON", flush=True)

try:
    from fastapi import FastAPI
    print("✅ FASTAPI IMPORTED", flush=True)

    app = FastAPI()

    # Combined route for GET and HEAD – this will definitely respond to Render's health check
    @app.api_route("/", methods=["GET", "HEAD"])
    def root():
        return {"status": "alive"}

    print("✅ APP CREATED SUCCESSFULLY", flush=True)

except Exception as e:
    print(f"❌ ERROR: {e}", flush=True)
    raise