const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp'];

function isValidImageFile(file) {
  if (!file) return false;
  if (ALLOWED_TYPES.includes(file.type)) return true;
  const fileName = file.name.toLowerCase();
  return ALLOWED_EXTENSIONS.some((ext) => fileName.endsWith(ext));
}

const tests = [
  { name: 'catalog_15025.jpg', type: 'image/jpeg', expected: true },
  { name: 'sample_product.png', type: 'image/png', expected: true },
  { name: 'modern_shoe.webp', type: 'image/webp', expected: true },
  { name: 'unsupported.txt', type: 'text/plain', expected: false },
  { name: 'archive_data.zip', type: 'application/zip', expected: false },
];

console.log('==================================================');
console.log('IMAGE UPLOADER FILE TYPE VALIDATION TEST SUITE');
console.log('==================================================');

let allPassed = true;
tests.forEach((t, idx) => {
  const result = isValidImageFile(t);
  const passed = result === t.expected;
  if (!passed) allPassed = false;
  const status = passed ? 'PASS' : 'FAIL';
  console.log(`[TEST ${idx + 1}] File: ${t.name.padEnd(20)} | Type: ${t.type.padEnd(16)} | Result: ${result} [${status}]`);
});

console.log('==================================================');
if (allPassed) {
  console.log('RESULT: ALL IMAGE VALIDATION TESTS PASSED SUCCESSFULLY.');
  process.exit(0);
} else {
  console.error('RESULT: VALIDATION TESTS FAILED.');
  process.exit(1);
}
