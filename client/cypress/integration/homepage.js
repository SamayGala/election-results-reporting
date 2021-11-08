import 'cypress-file-upload'

before(() => cy.exec('.\\cypress\\seed-test-db.sh'))

describe('renders the home page', () => {
  it('renders correctly', () => {
    cy.visit('/')
  })

  it('logins as a election admin', () => {
    cy.visit('/')
    cy.get('.bp3-button').click()
    cy.contains('Log in as an admin').click()
    cy.loginElectionAdmin('election-admin@example.com')
    cy.contains('Create New Election')
  })

  it('Create New Election', () => {
    cy.visit('/')
    cy.loginElectionAdmin('election-admin@example.com')
    cy.contains('Create New Election')
    cy.get('#electionName').clear()
    cy.get('#electionName').type('test2')
    cy.get('#electionDate').click()
    cy.get('#electionDate').type('2021-11-02')
    cy.get('#pollsOpen').click()
    cy.get('#pollsOpen').type('11:20')
    cy.get('#pollsClose').click()
    cy.get('#pollsClose').type('11:40')
    cy.get('#certificationDate').click()
    cy.get('#certificationDate').type('2021-11-02')
    cy.get(
      '[for="jurisdictions"] > .bp3-file-input > .bp3-file-upload-input'
    ).click()
    cy.fixture('CSVs/sample_jurisdiction_filesheet.csv').then((fileContent) => {
      cy.get('[for="jurisdictions"] > .bp3-file-input > input')
        .first()
        .attachFile({
          fileContent: fileContent.toString(),
          fileName: 'sample_jurisdiction_filesheet.csv',
          mimeType: 'text/csv',
        })
    })
    cy.get(
      '[for="definition"] > .bp3-file-input > .bp3-file-upload-input'
    ).click()
    cy.fixture('sample_election.json').then((fileContent) => {
      cy.get('[for="definition"] > .bp3-file-input > input')
        .first()
        .attachFile({
          fileContent: fileContent,
          fileName: 'election-upgraded-2020-07-28.json',
          mimeType: 'application/json',
        })
    })
    cy.get('.sc-iNiQyp > .bp3-button > .bp3-button-text').click()
    cy.get('.bp3-button-group > .bp3-button').click()
  })

  it('logins as a jurisdiction admin', () => {
    cy.visit('/admin')
    cy.loginJurisdictionAdmin('admin@rebelalliance.ninja')
    cy.get('#precinct').select('Antioch')
    cy.get('#totalBallotsCast').clear()
    cy.get('#totalBallotsCast').type('10')
    cy.get('#contests\\[0\\]\\.id').select('Circuit Clerk')
    cy.get('#contests\\[0\\]\\.candidates\\[0\\]\\.id').clear()
    cy.get('#contests\\[0\\]\\.candidates\\[0\\]\\.id').type('5')
    cy.get('#contests\\[0\\]\\.candidates\\[1\\]\\.id').clear()
    cy.get('#contests\\[0\\]\\.candidates\\[1\\]\\.id').type('5')
    cy.get('.bp3-large > .bp3-button-text').click()

    cy.contains('Election Results Status')
    cy.contains('1 out of 14 precinct results have been uploaded.')
    /* ==== Generated with Cypress Studio ==== */
    cy.get('.bp3-popover-target > .bp3-button > .bp3-button-text').click()
    cy.contains('Log out').click()
    cy.visit('/')
    /* ==== End Cypress Studio ==== */
  })
  it('login to election admin to see result', () => {
    cy.visit('/admin')
    cy.loginElectionAdmin('election-admin@example.com')
    cy.contains('Create New Election')
    cy.get('.bp3-button-group > .bp3-button').click()

    cy.get('.bp3-button-text > .bp3-icon > svg').click()
  })
})
