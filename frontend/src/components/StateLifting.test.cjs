// Node test script for parent-child state lifting flow

class MockApp {
  constructor() {
    this.selectedFile = null
  }

  setSelectedFile(file) {
    this.selectedFile = file
  }
}

class MockImageUploader {
  constructor(props) {
    this.props = props
  }

  selectFile(candidateFile) {
    if (this.props.onFileChange) {
      this.props.onFileChange(candidateFile)
    }
  }

  reset() {
    if (this.props.onFileChange) {
      this.props.onFileChange(null)
    }
  }
}

console.log('==================================================')
console.log('STATE LIFTING DATA FLOW VERIFICATION SUITE')
console.log('==================================================')

let allPassed = true

// 1. Initial State
const app = new MockApp()
console.log(`[TEST 1] Initial App state: selectedFile = ${app.selectedFile} [${app.selectedFile === null ? 'PASS' : 'FAIL'}]`)
if (app.selectedFile !== null) allPassed = false

// 2. Component instantiates with parent state
let uploader = new MockImageUploader({
  file: app.selectedFile,
  onFileChange: (file) => app.setSelectedFile(file)
})

// 3. User selects an image
const file1 = { name: '15025.jpg', size: 12358, type: 'image/jpeg' }
uploader.selectFile(file1)
console.log(`[TEST 2] Selected image 1: Parent state updated to '${app.selectedFile ? app.selectedFile.name : null}' [${app.selectedFile === file1 ? 'PASS' : 'FAIL'}]`)
if (app.selectedFile !== file1) allPassed = false

// 4. User resets/removes image
uploader.reset()
console.log(`[TEST 3] Reset image: Parent state cleared to '${app.selectedFile}' [${app.selectedFile === null ? 'PASS' : 'FAIL'}]`)
if (app.selectedFile !== null) allPassed = false

// 5. User selects second image
const file2 = { name: '17888.jpg', size: 2267, type: 'image/jpeg' }
uploader.selectFile(file2)
console.log(`[TEST 4] Selected image 2: Parent state updated to '${app.selectedFile ? app.selectedFile.name : null}' [${app.selectedFile === file2 ? 'PASS' : 'FAIL'}]`)
if (app.selectedFile !== file2) allPassed = false

console.log('==================================================')
if (allPassed) {
  console.log('RESULT: ALL STATE LIFTING FLOW TESTS PASSED.')
  process.exit(0)
} else {
  console.error('RESULT: TESTS FAILED.')
  process.exit(1)
}
