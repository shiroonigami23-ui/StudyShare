const express = require('express');
const multer = require('multer');
const fs = require('fs');
const path = require('path');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 3000;
const UPLOADS_DIR = path.join(__dirname, 'uploads');

app.use(cors());
app.use(express.json());

// Ensure uploads directory exists
if (!fs.existsSync(UPLOADS_DIR)) fs.mkdirSync(UPLOADS_DIR);

let filesMeta = []; // In-memory store for files and metadata

// Helper: Save metadata to disk (for persistence across restarts)
function saveMeta() {
  fs.writeFileSync(path.join(UPLOADS_DIR, 'meta.json'), JSON.stringify(filesMeta, null, 2));
}

// Helper: Load metadata from disk
function loadMeta() {
  try {
    filesMeta = JSON.parse(fs.readFileSync(path.join(UPLOADS_DIR, 'meta.json')));
  } catch {
    filesMeta = [];
  }
}
loadMeta();

// Multer setup for file uploads
const storage = multer.diskStorage({
  destination: UPLOADS_DIR,
  filename: (req, file, cb) => {
    const unique = Date.now() + '-' + Math.round(Math.random() * 1e9);
    cb(null, unique + '-' + file.originalname);
  }
});
const upload = multer({ storage, limits: { fileSize: 10 * 1024 * 1024 } });

// Admin authorization middleware
function adminAuth(req, res, next) {
  const pw = req.headers['x-admin-password'] || req.body.password;
  if (pw === process.env.ADMIN_PASSWORD) {
    next();
  } else {
    res.status(401).json({ error: 'Unauthorized' });
  }
}

// Upload endpoint (all uploads start as unapproved except admin uploads)
app.post('/upload', upload.single('file'), (req, res) => {
  if (!req.file || !req.body.uploader) return res.status(400).json({ error: 'Missing file or uploader name' });

  const isUploaderAdmin = req.body.uploader.toLowerCase() === 'admin';
  const meta = {
    id: req.file.filename, // unique id
    originalname: req.file.originalname,
    uploader: req.body.uploader,
    uploadDate: new Date().toISOString(),
    downloads: 0,
    upvotes: 0,
    approved: isUploaderAdmin,
    comments: []
  };
  filesMeta.unshift(meta);
  saveMeta();
  res.json({ success: true, file: meta });
});

// List files endpoint (admins see all, users only approved)
app.get('/files', (req, res) => {
  const isAdmin = req.headers['x-admin-password'] === process.env.ADMIN_PASSWORD;
  if (isAdmin) {
    res.json(filesMeta);
  } else {
    res.json(filesMeta.filter(f => f.approved));
  }
});

// Download endpoint (+increment download count)
app.get('/download/:id', (req, res) => {
  const meta = filesMeta.find(f => f.id === req.params.id);
  if (!meta) return res.status(404).json({ error: 'Not found' });

  // Only approve downloads for approved files or admin
  const isAdmin = req.headers['x-admin-password'] === process.env.ADMIN_PASSWORD;
  if (!meta.approved && !isAdmin) {
    return res.status(403).json({ error: 'File not approved for download' });
  }

  const filepath = path.join(UPLOADS_DIR, req.params.id);
  if (!fs.existsSync(filepath)) return res.status(404).json({ error: 'File missing' });

  meta.downloads = (meta.downloads || 0) + 1;
  saveMeta();
  res.download(filepath, meta.originalname);
});

// Upvote file
app.post('/upvote/:id', (req, res) => {
  const meta = filesMeta.find(f => f.id === req.params.id);
  if (!meta) return res.status(404).json({ error: 'File not found' });

  meta.upvotes = (meta.upvotes || 0) + 1;
  saveMeta();
  res.json({ success: true, upvotes: meta.upvotes });
});

// Post a comment (with optional parentId for replies)
app.post('/comment', (req, res) => {
  const { name, text, parentId } = req.body;
  if (!name || !text) return res.status(400).json({ error: 'Name and text required' });

  // Find which file this comment belongs to — if parentId is set for parent comment, find file by parent comment id not supported yet, so assume flat for now
  // To keep simple, just append comments globally for demo:
  // You may enhance logic to store comments per file for real production use

  // For demo, just store comments in a global array inside filesMeta or separately
  if (!Array.isArray(filesMeta.comments)) filesMeta.comments = [];
  filesMeta.comments.push({ id: Date.now() + '-' + Math.round(Math.random() * 1e9), name, text, parentId: parentId || null, date: new Date().toISOString() });

  saveMeta();
  res.json({ success: true, comments: filesMeta.comments });
});

// Get all comments
app.get('/comments', (req, res) => {
  res.json(filesMeta.comments || []);
});

// Approve a file (admin only)
app.post('/approve/:id', adminAuth, (req, res) => {
  const file = filesMeta.find(f => f.id === req.params.id);
  if (!file) return res.status(404).json({ error: 'File not found' });
  file.approved = true;
  saveMeta();
  res.json({ success: true });
});

// Reject (delete) file (admin only)
app.delete('/reject/:id', adminAuth, (req, res) => {
  const index = filesMeta.findIndex(f => f.id === req.params.id);
  if (index === -1) return res.status(404).json({ error: 'File not found' });

  const file = filesMeta[index];
  const filepath = path.join(UPLOADS_DIR, file.id);
  if (fs.existsSync(filepath)) fs.unlinkSync(filepath);

  filesMeta.splice(index, 1);
  saveMeta();
  res.json({ success: true });
});

// Delete file endpoint (admin or uploader can delete)
app.delete('/delete/:id', adminAuth, (req, res) => {
  const index = filesMeta.findIndex(f => f.id === req.params.id);
  if (index === -1) return res.status(404).json({ error: 'File not found' });

  // Optional: check uploader matches or allow admin
  const file = filesMeta[index];
  // In a real system, verify uploader in req.body or token
  const isAdmin = req.headers['x-admin-password'] === process.env.ADMIN_PASSWORD;
  if (!isAdmin && req.body.uploader !== file.uploader) {
    return res.status(403).json({ error: 'Forbidden' });
  }

  const filepath = path.join(UPLOADS_DIR, file.id);
  if (fs.existsSync(filepath)) fs.unlinkSync(filepath);

  filesMeta.splice(index, 1);
  saveMeta();
  res.json({ success: true });
});

// Serve uploaded files statically (optionally used internally)
app.use('/uploads', express.static(UPLOADS_DIR));

// Root endpoint (basic health check)
app.get('/', (req, res) => {
  res.send('ShareLit backend is running!');
});

// Start server
app.listen(PORT, () => {
  console.log(`Server is listening on port ${PORT}`);
});
