from locust import HttpUser, task, between


class BacteriaUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def view_home(self):
        self.client.get("/")

    @task(1)
    def view_dashboard(self):
        self.client.get("/api/dashboard")

    @task(1)
    def list_bacteria(self):
        self.client.get("/api/bacteria")
