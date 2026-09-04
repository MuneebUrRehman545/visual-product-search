# Visual Product Search — Video Demo Script & Presentation Guide

**Project**: Visual Product Search System  
**Duration**: 3–5 Minutes  
**Target Audience**: Technical Assessors, Hiring Managers, and Engineers  
**Presenter**: Machine Learning Engineer / Full-Stack Developer  

---

## 🎬 Video Presentation Outline & Timeline

```text
⏱️ 0:00 – 0:30 | Section 1: Problem Statement & Application Goal
⏱️ 0:30 – 1:00 | Section 2: End-to-End System & Database Architecture
⏱️ 1:00 – 2:00 | Section 3: Live Visual Search Demonstration (Clean & Messy)
⏱️ 2:00 – 2:40 | Section 4: Empirical Benchmark: OpenCLIP vs. ResNet-50
⏱️ 2:40 – 3:20 | Section 5: Second-Stage Visual Re-ranking (Color Histograms)
⏱️ 3:20 – 4:00 | Section 6: Messy Query Robustness & Transformation Analysis
⏱️ 4:00 – 4:30 | Section 7: Cloud Deployment, Stable ID Mapping & Conclusion
```

---

## 🎙️ Detailed Speaking Script

### ⏱️ 0:00 – 0:30 | Section 1: Problem Statement & Application Goal
**Visual Cue**: *Screen sharing the React web application homepage.*

> **Spoken**:  
> "Welcome! In modern e-commerce, users often know the exact style, pattern, or aesthetic they want to buy, but lack the precise text keywords to describe it.
> 
> To solve this, we built a production-grade **Visual Product Search Engine** that allows users to upload any photo—from a clean studio catalog shot to a smartphone snapshot—and instantly retrieves visually and semantically similar items across a catalog of over **44,000 fashion products** in under 150 milliseconds."

---

### ⏱️ 0:30 – 1:00 | Section 2: System Architecture & Separation of Concerns
**Visual Cue**: *Show the system architecture diagram from README.md / slides.*

> **Spoken**:  
> "To achieve both millisecond-level retrieval speed and enterprise data persistence, our architecture separates indexing from storage:
> 
> 1. **Client**: A React Single Page Application deployed on Vercel captures image uploads and sends multipart requests.
> 2. **Backend**: A FastAPI service extracts 512-dimensional vector embeddings using a cached OpenCLIP Vision Transformer.
> 3. **Fast Vector Retrieval**: We use **FAISS `IndexIDMap2`** to perform approximate nearest-neighbor cosine similarity search over all 44,119 items in less than 20 milliseconds.
> 4. **Persistent System of Record**: Instead of storing all metadata in memory, FAISS returns stable catalog item integer IDs, which the backend uses to perform an order-preserving batch SQL lookup against a hosted **PostgreSQL database with `pgvector`**.
> 
> This guarantees zero data desynchronization between vector indexing and relational catalog metadata."

---

### ⏱️ 1:00 – 2:00 | Section 3: Live Visual Search Demonstration
**Visual Cue**: *Upload `data/images/37783.jpg` (Navy Blue John Players Shirt).*

> **Spoken**:  
> "Let’s see the system in action. I’ll start by uploading a clean query image: a men's navy blue casual shirt.
> 
> *[Clicks Search]*
> 
> Within 140 milliseconds, the backend returns our top ranked matches. Notice that the top 5 results are all John Players shirts in matching subcategories, with similarity scores above 88% and accurate metadata badges—display title, master category, article type, color, and gender.
> 
> *[Uploads distorted image: `messy_test_q001_crop.jpg` (Cropped magenta top)]*
> 
> Now, let's test real-world camera noise. Here is a tightly cropped, off-center photo. Even with 15% of the outer boundary missing, the OpenCLIP model correctly isolates the garment’s key features and returns matching women’s tops and t-shirts with high confidence."

---

### ⏱️ 2:00 – 2:40 | Section 4: Empirical Benchmark (OpenCLIP vs. ResNet-50)
**Visual Cue**: *Display the final evaluation comparison table from docs/evaluation-report.md.*

> **Spoken**:  
> "Before deploying, we conducted a rigorous comparative evaluation against 200 held-out clean test queries and 200 messy queries. We benchmarked our multimodal **OpenCLIP ViT-B-32** against a classical **ResNet-50** deep convolutional baseline across identical catalog rows and hand-verified ground truth.
> 
> The results were decisive:
> - OpenCLIP achieved a **Recall@5 of 36.1%**, outperforming ResNet-50’s **26.9%**—a **+34.1% relative improvement**.
> - OpenCLIP achieved a **Precision@1 of 28.5%** compared to ResNet’s **23.5%**.
> - Furthermore, OpenCLIP’s 512-dimensional vector space reduced FAISS search latency by nearly 3x (18.9 ms vs 54.2 ms) and reduced total database storage footprint from 353 MB down to 88 MB."

---

### ⏱️ 2:40 – 3:20 | Section 5: Second-Stage Visual Re-ranking
**Visual Cue**: *Show the re-ranking parameter sweep chart / grid search summary.*

> **Spoken**:  
> "To investigate whether secondary visual cues could enhance retrieval, we implemented a modular **HSV color histogram re-ranking service**.
> 
> We precomputed 64-dimensional color histograms for all 44,119 catalog items and executed a 40-configuration grid sweep across our validation query split.
> 
> Our sweep showed that OpenCLIP’s multimodal representation already inherently encodes strong color and semantic alignment. Blending moderate color weights ($w_{\text{color}} \le 0.30$) maintained optimal Precision@5, while excessive color weights risked prioritizing background color over garment category. We froze this configuration to ensure reproducible deployment."

---

### ⏱️ 3:20 – 4:00 | Section 6: Messy Query Robustness Analysis
**Visual Cue**: *Show the breakdown table by transformation type.*

> **Spoken**:  
> "In e-commerce, user photos suffer from poor lighting, defocus, and awkward angles. We evaluated 8 distinct synthetic distortions on our test queries:
> 
> - **High Resilience**: Minor rotation ($\pm 8^\circ$) and darker lighting maintained strong performance with hit rates up to 48%.
> - **Vulnerabilities**: Defocus blur and artificial background padding caused the steepest drop in precision. Notably, ResNet-50 experienced complete failure on blurred images (0.0% recall), whereas OpenCLIP maintained partial semantic recognition."

---

### ⏱️ 4:00 – 4:30 | Section 7: Cloud Deployment & Conclusion
**Visual Cue**: *Show public deployment URLs, Swagger UI at `/docs`, and database connection.*

> **Spoken**:  
> "In conclusion:
> - The application is fully deployed with a **React frontend on Vercel**, a **FastAPI backend on cloud container hosting**, and **hosted PostgreSQL with `pgvector`**.
> - Every vector is connected to an immutable `catalog_item.id`, ensuring complete auditability and zero ID drift.
> - The codebase is fully open-source, modular, and accompanied by comprehensive evaluation reports and automated test suites.
> 
> Thank you for watching!"

---

## 📋 Presenter Checklist Before Recording

1. Ensure backend is running locally (`uvicorn app.main:app`) or live on cloud URL.
2. Ensure frontend dev server is running on `http://localhost:5173`.
3. Have sample query images ready on desktop:
   - `data/images/37783.jpg` (Clean John Players shirt)
   - `evaluation/queries/messy/messy_test_q001_crop.jpg` (Cropped top)
   - `data/images/22096.jpg` (White shoes)
4. Open browser tabs:
   - Tab 1: React Frontend UI (`http://localhost:5173`)
   - Tab 2: FastAPI Swagger Docs (`http://127.0.0.1:8000/docs`)
   - Tab 3: Evaluation Report (`docs/evaluation-report.md`)
