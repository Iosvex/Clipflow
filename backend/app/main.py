print("✅✅✅ HELLO FROM PYTHON", flush=True)

try:
    from fastapi import FastAPI
    print("✅ FASTAPI IMPORTED", flush=True)

    app = FastAPI()

    @app.get("/")
    def root():
        return {"status": "alive"}

    @app.head("/")
    def root_head():
        return {}

    print("✅ APP CREATED SUCCESSFULLY", flush=True)

except Exception as e:
    print(f"❌ ERROR: {e}", flush=True)
    raise