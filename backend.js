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

let filesMeta = []; // In-memory store for demo (use DB for prod)

// Helper: Save metadata to disk (for reboot safety)
function saveMeta() {
  fs.writeFileSync(path.join(UPLOADS_DIR, 'meta.json'), JSON.stringify(filesMeta, null, 2));
}

function loadMeta() {
  try {
    filesMeta = JSON.parse(fs.readFileSync(path.join(UPLOADS_DIR, 'meta.json')));
  } catch {
    filesMeta = [];
  }
}
loadMeta();

// Multer setup for uploads
const storage = multer.diskStorage({
  destination: UPLOADS_DIR,
  filename: (req, file, cb) => {
    const unique = Date.now() + '-' + Math.round(Math.random() * 1e9);
    cb(null, unique + '-' + file.originalname);
  }
});
const upload = multer({ storage, limits: { fileSize: 10 * 1024 * 1024 } });

// Middleware to check admin authorization via simple password header or body (for demo only)
function adminAuthMiddleware(req, res, next) {
  const password = req.headers['x-admin-password'] || req.body.password;
  if (password === process.env.ADMIN_PASSWORD) {
    next();
  } else {
    res.status(401).json({ error: 'Unauthorized' });
  }
}

// Upload endpoint
app.post('/upload', upload.single('file'), (req, res) => {
  if (!req.file || !req.body.uploader) return res.status(400).json({ error: 'Missing file or uploader name' });

  // Set approved true if uploader is admin, false otherwise
  const isAdmin = req.body.uploader.toLowerCase() === 'admin';
  const meta = {
    id: req.file.filename, // unique id
    originalname: req.file.originalname,
    uploader: req.body.uploader,
    uploadDate: new Date().toISOString(),
    downloads: 0,
    upvotes: 0,
    approved: isAdmin,     // admin uploads auto approved
    comments: []
  };
  filesMeta.unshift(meta);
  saveMeta();
  res.json({ success: true, file: meta });
});

// List files endpoint (only approved files for non-admins)
app.get('/files', (req, res) => {
  const isAdmin = req.headers['x-admin-password'] === process.env.ADMIN_PASSWORD;
  if (isAdmin) {
    res.json(filesMeta); // send all for admin
  } else {
    res.json(filesMeta.filter(f => f.approved)); // only approved for users
  }
});

// Download endpoint (+counts)
app.get('/download/:id', (req, res) => {
  const meta = filesMeta.find(f => f.id === req.params.id);
  if (!meta) return res.status(404).json({ error: 'Not found' });

  if (!meta.approved && req.headers['x-admin-password'] !== process.env.ADMIN_PASSWORD) {
    return res.status(403).json({ error: 'Not approved for download' });
  }

  const filepath = path.join(UPLOADS_DIR, req.params.id);
  if (!fs.existsSync(filepath)) return res.status(404).json({ error: 'File missing' });

  meta.downloads = (meta.downloads || 0) + 1;
  saveMeta();
  res.download(filepath, meta.originalname);
});

// Approve file (Admin only)
app.post('/approve/:id', adminAuthMiddleware, (req, res) => {
  const meta = filesMeta.find(f => f.id === req.params.id);
  if (!meta) return res.status(404).json({ error: 'File not found' });
  meta.approved = true;
  saveMeta();
  res.json({ success: true });
});

// Reject file (Admin only)
app.delete('/reject/:id', adminAuthMiddleware, (req, res) => {
  const index = filesMeta.findIndex(f => f.id === req.params.id);
  if (index === -1) return res.status(404).json({ error: 'File not found' });

  // Delete file from disk too
  const filepath = path.join(UPLOADS_DIR, filesMeta[index].id);
  if (fs.existsSync(filepath)) fs.unlinkSync(filepath);

  filesMeta.splice(index, 1);
  saveMeta();
  res.json({ success: true });
});

// Delete file (Admin can delete any; user can delete own)
app.delete('/delete/:id', (req, res) => {
  const { uploader, adminPassword } = req.body;
  const index = filesMeta.findIndex(f => f.id === req.params.id);
  if (index === -1) return res.status(404).json({ error: 'File not found' });

  const fileMeta = filesMeta[index];
  const isAdmin = adminPassword === process.env.ADMIN_PASSWORD;
  if (!isAdmin && fileMeta.uploader !== uploader) {
    return res.status(403).json({ error: 'Forbidden: Not allowed to delete this file' });
  }

  // Delete file from disk
  const filepath = path.join(UPLOADS_DIR, fileMeta.id);
  if (fs.existsSync(filepath)) fs.unlinkSync(filepath);

  filesMeta.splice(index, 1);
  saveMeta();
  res.json({ success: true });
});

// Upvote file
app.post('/upvote/:id', (req, res) => {
  const meta = filesMeta.find(f => f.id === req.params.id);
  if (!meta) return res.status(404).json({ error: 'File not found' });

  meta.upvotes = (meta.upvotes || 0) + 1;
  saveMeta();
  res.json({ success: true, upvotes: meta.upvotes });
});

// Post a comment with optional parentId for replies
app.post('/comment', (req, res) => {
  const { name, text, parentId } = req.body;
  if (!name || !text) return res.status(400).json({ error: 'Name and text required' });

  // For simplicity store comments globally (not per file, as per frontend spec)
  // You can adapt to store per file if needed
  if (!Array.isArray(filesMeta.comments)) filesMeta.comments = [];
  filesMeta.comments.push({
    id: Date.now() + '-' + Math.round(Math.random() * 1e9),
    name,
    text,
    parentId: parentId || null,
    date: new Date().toISOString()
  });
  saveMeta();
  res.json({ success: true, comments: filesMeta.comments });
});

// Get all comments
app.get('/comments', (req, res) => {
  res.json(filesMeta.comments || []);
});

// Admin dashboard: simple example endpoint (protected)
app.post('/admin', (req, res) => {
  const { password } = req.body;
  if (password !== process.env.ADMIN_PASSWORD)
    return res.status(401).json({ error: 'Unauthorized' });
  res.json({ files: filesMeta });
});

// Serve uploaded files (optional direct access)
app.use('/uploads', express.static(UPLOADS_DIR));

// Basic root endpoint
app.get('/', (req, res) => {
  res.send('ShareLit backend is running!');
});

app.listen(PORT, () => {
  console.log('Server running on', PORT);
});
