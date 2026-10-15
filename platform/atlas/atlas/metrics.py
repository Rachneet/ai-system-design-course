from prometheus_client import Counter

submissions = Counter("atlas_submissions_total", "Submissions by kind and outcome", ["kind", "outcome"])
reviews = Counter("atlas_reviews_total", "Review decisions", ["kind", "decision"])
downloads = Counter("atlas_downloads_total", "Discovery reads", ["kind"])
