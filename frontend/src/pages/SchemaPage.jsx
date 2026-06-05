import Header from '../components/Header'
import SchemaExplorer from '../components/SchemaExplorer'
import '../App.css'

export default function SchemaPage() {
  return (
    <div className="app">
      <Header activePage="schema" />
      <SchemaExplorer />
    </div>
  )
}
