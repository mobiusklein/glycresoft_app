class Application extends ActionLayerManager
    constructor: (options={}) ->
        super options.actionContainer, options

        @version = [
            0
            0
            1
        ]

        @context = {}
        @settings = {}
        @tasks = {}
        @sideNav = $('.side-nav')
        @colors = new ColorManager()
        self = this

        self.monosaccharideFilterState = new MonosaccharideFilterState(self, null)

        @messageHandlers = {}

        @connectEventSource()


        @handleMessage "log", (data) =>
            console.log(data)
            return

        @handleMessage 'update', (data) =>
            Materialize.toast data.replace(/"/g, ''), 4000
            return

        @handleMessage 'refresh-index', (data) =>
            self.loadData()
        @handleMessage 'task-queued', (data) =>
            self.tasks[data.id] = Task.create
                'id': data.id
                'name': data.name
                "created_at": data.created_at
                'status': 'queued'
            self.updateTaskList()
            return
        @handleMessage 'task-start', (data) =>
            self.tasks[data.id] = Task.create
                'id': data.id
                'name': data.name
                "created_at": data.created_at
                'status': 'running'
            self.updateTaskList()
            return
        @handleMessage 'task-error', (data) =>
            task = self.tasks[data.id]
            task.status = 'error'
            self.updateTaskList()
            return
        @handleMessage 'task-complete', (data) =>
            try
                self.tasks[data.id].status = 'finished'
            catch err
                self.tasks[data.id] = Task.create
                    'id': data.id
                    'name': data.name
                    "created_at": data.created_at
                    'status': 'finished'
            self.updateTaskList()
            return
        @handleMessage "task-stopped", (data) =>
            try
                self.tasks[data.id].status = 'stopped'
            catch err
                self.tasks[data.id] = Task.create
                    'id': data.id
                    'name': data.name
                    'status': 'stopped'
            self.updateTaskList()
            return
        @handleMessage 'new-sample-run', (data) =>
            @samples[data.name] = data
            @emit "render-samples"
        @handleMessage 'new-hypothesis', (data) =>
            @hypotheses[data.uuid] = Hypothesis.create(data)
            @emit "render-hypotheses"
        @handleMessage 'new-analysis', (data) =>
            @analyses[data.uuid] = data
            @emit "render-analyses"

        @on "layer-change", (data) =>
            @colors.update()

    setUser: (userId, callback) ->
        User.set(userId, (userId) =>
            @eventStream.close()
            @connectEventSource()
            @loadData()
            Materialize.toast("Logged in as #{userId.user_id}")
        )
        if callback?
            callback()

    getUser: (callback) ->
        User.get((userId) -> callback(userId.user_id))

    connectEventSource: ->
        @eventStream = new EventSource('/stream')

    runInitializers: ->
        for initializer in Application.initializers
            initializer.apply this, null

    updatePreferences: (payload={}) ->
        $.post('/preferences', payload).success((data) =>
            for k, v of data
                @settings[k] = v
            @emit("update_settings")
        ).error (err) ->
            console.log "error in updatePreferences", err, arguments

    updateTaskList: (clearFinished=true) ->
        taskListContainer = @sideNav.find('.task-list-container ul')

        clickTask = (event) ->
            handle = $(this)
            state = handle.attr('data-status')
            id = handle.attr('data-id')
            if (state == 'finished' or state == 'stopped') and event.which != 3
                delete self.tasks[id]
                handle.fadeOut()
                handle.remove()
            return
        self = @

        viewLog = (event) ->
            handle = $(this)
            id = handle.attr('data-id')
            name = handle.attr("data-name")
            created_at = handle.attr("data-created-at")
            state = {}
            modal = $("#message-modal")
            updateWrapper = () ->
                updater = ->
                    status = taskListContainer.find("li[data-id='#{id}']").attr('data-status')
                    if status == "running" or status == "queued"
                        $.get("/internal/log/#{name}-#{created_at}").success(
                            (message) ->
                                console.log "Updating Log Window..."
                                modalContent = modal.find(".modal-content")
                                modalContent.html message
                                # modal.animate({scrollTop: modal[0].scrollHeight},"fast");
                            )
                state.intervalId = setInterval(updater, 5000)
            completer = ->
                clearInterval(state.intervalId)

            $.get("/internal/log/#{name}-#{created_at}").success(
                (message) => self.displayMessageModal(message, {
                    "ready": updateWrapper, "complete": completer})).error(
                (err) => alert("An error occurred during retrieval. #{err.toString()}"))

        cancelTask = (event) ->
            userInput = window.confirm("Are you sure you want to cancel this task?")
            if userInput
                handle = $(this)
                id = handle.attr('data-id')
                $.get "/internal/cancel_task/" + id

        taskListContainer.html("")
        taskListContainer.append(_.map(
            _.sortBy(_.values(@tasks), ["createdAt"]), renderTask))
        taskListContainer.find('li').map (i, li) -> contextMenu li, {
            "View Log": viewLog
            "Cancel Task": cancelTask
        }
        taskListContainer.find('li').click clickTask
        taskListContainer.find("li").dblclick viewLog

    handleMessage: (messageType, handler) ->
        @messageHandlers[messageType] = handler
        @eventStream.addEventListener messageType, (event) ->
            data = JSON.parse(event.data)
            handler(data)

    @initializers = [
        ->
            self = @
            $ ->
                self.container = $(self.options.actionContainer)
                self.sideNav = $('.side-nav')
                self.addLayer ActionBook.home
                $("#search-glycan-composition").click (event) ->
                    self.addLayer ActionBook.glycanCompositionSearch
                    self.setShowingLayer self.lastAdded
                $("#search-glycopeptide-database").click (event) ->
                    self.addLayer ActionBook.glycopeptideSequenceSearch
                    self.setShowingLayer self.lastAdded
                $("#add-sample").click (event) ->
                    self.addLayer ActionBook.addSample
                    self.setShowingLayer self.lastAdded
                $("#add-sample-to-workspace").click (event) ->
                    self.addLayer ActionBook.addSample
                    self.setShowingLayer self.lastAdded
                $("#build-glycan-search-space").click (event) ->
                    self.addLayer ActionBook.naiveGlycanSearchSpace
                    self.setShowingLayer self.lastAdded
                $("#build-glycopeptide-search-space").click (event) ->
                    self.addLayer ActionBook.naiveGlycopeptideSearchSpace
                    self.setShowingLayer self.lastAdded
                $("#import-existing-hypothesis").click (event) ->
                    self.uploadHypothesis()
                $("#import-existing-sample").click (event) ->
                    self.uploadSample()
        ->
            @loadData()
        ->
            @handleMessage "files-to-download", (data) =>
                for file in data.files
                    @downloadFile(file)
        ->
            @on "update_settings", =>
                layer = @getShowingLayer()
                if layer.name != ActionBook.home.name
                    console.log("Updated Settings, Current Layer:", layer.name)
                    layer.setup()

        ->
            setInterval(@_upkeepIntervalCallback, @options.upkeepInterval || 10000)

            refreshTasks = =>
                TaskAPI.all (d) =>
                    for key, task of d
                        @tasks[key] = task
                    @updateTaskList()

            setInterval(refreshTasks, @options.refreshTasksInterval || 250000)
    ]

    loadData: ->
        HypothesisAPI.all (d) =>
            @hypotheses = convertMapping(Hypothesis.create)(d)
            @emit "render-hypotheses"
        SampleAPI.all (d) =>
            @samples = d
            @emit "render-samples"
        AnalysisAPI.all (d) =>
            @analyses = d
            @emit "render-analyses"
        TaskAPI.all (d) =>
            for key, data of d
                d[key] = Task.create(data)
            @tasks = d
            @updateTaskList()
        MassShiftAPI.all (d) =>
            @massShifts = d
        @colors.update()

    downloadFile: (filePath) ->
        window.location = "/internal/file_download/" + btoa(filePath)

    displayMessageModal: (message, modalArgs) ->
        container = $("#message-modal")
        container.find('.modal-content').html message
        $(".lean-overlay").remove()
        container.openModal(modalArgs)

    closeMessageModal: ->
        container = $("#message-modal")
        container.closeModal()

    ajaxWithContext: (url, options) ->
        if !options?
            options = {data:{}}
        data = options.data
        data['settings'] = @settings
        data['context'] = @context
        options.method = "POST"
        options.data = JSON.stringify(data)
        options.contentType = "application/json"
        return $.ajax(url, options)

    _upkeepIntervalCallback: =>
        if @eventStream.readyState == 2
            console.log "Re-establishing EventSource"
            @connectEventSource()
            for msgType, handler of @messageHandlers
                @handleMessage msgType, handler
        return true

    setHypothesisContext: (hypothseisUUID) ->
        @context.hypothseisUUID = hypothseisUUID

    invalidate: ->
        @monosaccharideFilterState.invalidate()
        console.log("Invalidated")

    isNativeClient: ->
        window.nativeClientKey?

    notifyUser: (message, duration) ->
        if not duration?
            duration = 4000
        Materialize.toast(message, duration)

    uploadHypothesis: ->
        fileInput = $("<input type='file' />")
        self = this
        fileInput.change (event) ->
            if @files.length == 0
                return
            form = new FormData()
            if self.isNativeClient()
                form.append("native-hypothesis-file-path", @files[0].path)
            else
                form.append('hypothesis-file', @files[0])
            rq = new XMLHttpRequest()
            rq.open("POST", "/import_hypothesis")
            rq.send(form)
        fileInput[0].click()

    uploadSample: ->
        fileInput = $("<input type='file' />")
        self = this
        fileInput.change (event) ->
            if @files.length == 0
                return
            form = new FormData()
            if self.isNativeClient()
                form.append("native-sample-file-path", @files[0].path)
            else
                form.append('sample-file', @files[0])
            rq = new XMLHttpRequest()
            rq.open("POST", "/import_sample")
            rq.send(form)
        fileInput[0].click()



createdAtParser = /(\d{4})-(\d{2})-(\d{2})\s(\d+)-(\d+)-(\d+(?:\.\d*)?)/


class Task
    @create: (obj) ->
        return new Task(obj.id, obj.status, obj.name, obj.created_at)

    constructor: (@id, @status, @name, @created_at) ->
        [_, year, month, day, hour, minute, seconds] = @created_at.match(createdAtParser)
        @createdAt = new Date(year, month, day, hour, minute, seconds)



renderTask = (task) ->
    name = task.name
    status = task.status
    id = task.id
    created_at = task.created_at
    element = $("<li class='task-display' data-id=\'#{id}\' data-status=\'#{status}\' data-name=\'#{name}\' data-created-at=\'#{created_at}\'><b>#{name}</b> (#{status})</li>")
    element.attr("data-name", name)
    element


class Hypothesis
    constructor: (@name, @id, @uuid, @path, @hypothesis_type, @monosaccharide_bounds, @decoy_hypothesis, options) ->
        if options?
            @options = options
        else
            @options = {}

    isFullCrossproduct: ->
        if @options.full_crossproduct?
            return @options.full_crossproduct
        return true

    hasDecoyDatabase: ->
        return @decoy_hypothesis?

    @create: (source) ->
        return new Hypothesis source.name, source.id, source.uuid, source.path, source.hypothesis_type,
                              source.monosaccharide_bounds, source.decoy_hypothesis, source.options